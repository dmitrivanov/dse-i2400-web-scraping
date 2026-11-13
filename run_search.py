"""One query/provider ETL workflow with cache-first search and explicit collection."""
import argparse
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from mysql.connector import Error

import db
from capture_page import CaptureError, capture_search_page
from ocr_capture import extract_screenshot_text
from clean_urls import clean_results, url_evidence_counts
from config import get_collection_page_limit, get_scraper_config
from google_search import SearchError
from saved_searches import find_saved_collection, provider_for_run, collection_metadata_for_run
from search_providers import get_provider

FILLER_WORDS = {"a", "an", "the", "and", "or", "not", "of", "in", "on", "at", "to", "for", "with", "please"}


def validate_query(query: str) -> None:
    """Count five alphabetic tokens excluding explicit fillers/Boolean operators."""
    words = re.findall(r"[^\W\d_]+", query.lower(), flags=re.UNICODE)
    if len(query) > 1000:
        raise ValueError("Query must contain at most 1000 characters")
    if sum(word not in FILLER_WORDS for word in words) < 5:
        raise ValueError("Query must contain at least five meaningful words")


class CollectionError(ValueError):
    """Safe actionable collection validation message for the local interface."""


class PaidRequestRequired(CollectionError):
    """A cache miss needs deliberate authorization before any paid page request."""


def run_search(query: str, max_pages: int | None = None, fetcher: str | None = None,
               engine: str = "google", capture: bool = False, mode: str = "search",
               refresh: bool = False, resume_run_id: int | None = None,
               allow_paid: bool = False) -> dict:
    """Cache first, authorize a bounded budget, then commit each actual result page."""
    validate_query(query)
    provider, fetcher, fetch_page = get_provider(engine, fetcher)
    if mode not in {"search", "collect"}:
        raise CollectionError("Mode must be search or collect")
    target = 50 if mode == "collect" else 1
    limit = get_collection_page_limit() if max_pages is None and mode == "collect" else (1 if max_pages is None else max_pages)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise CollectionError("Page limit must be an integer from 1 to 20")
    if mode == "search" and limit != 1:
        raise CollectionError("Normal search uses one page; choose Collect 50 for pagination")
    if resume_run_id is not None and (mode != "collect" or refresh):
        raise CollectionError("Collect More requires collect mode without refresh")
    saved = None
    if not refresh and resume_run_id is None:
        saved = find_saved_collection(query, engine, provider, target)
    existing, start, pages = [], 0, 0
    if resume_run_id is not None:
        saved = db.get_search_run(resume_run_id)
        if (not saved or saved["run"]["query_text"] != query or saved["run"]["engine"] != engine
                or provider_for_run(saved["run"]) != provider or saved["run"]["status"] not in {"completed", "failed"}):
            raise CollectionError("Collect More requires a matching saved query/provider and a finished run")
    if saved:
        existing, counts = clean_results(saved["results"], preserve_urls=engine == "google")
        evidence = url_evidence_counts(existing)
        qualifies = evidence["direct_url_count"] if target == 50 else counts["final_count"]
        if saved["run"]["status"] == "completed" and (qualifies >= target or (resume_run_id is None and counts["final_count"] >= target)):
            summary = {"run_id": saved["run"]["id"], "engine": engine, "provider": provider,
                       "fetcher": fetcher, "status": "completed", "pages": 0, "reused": True,
                       "target_count": target, "observed_target_met": counts["final_count"] >= target,
                       "target_met": qualifies >= target, **counts, **evidence, "error": None}
            if capture:
                summary["capture"] = capture_run(query, saved["run"]["id"], engine=engine)
            return summary
        if resume_run_id is None:
            existing = []
        else:
            meta = collection_metadata_for_run(saved["run"])
            pages = meta.get("pages")
            if type(pages) is not int or pages < 1:
                raise CollectionError("Saved page provenance is unavailable; use Refresh to start a new collection")
            start = meta.get("next_start", pages * 10 if engine == "google" else None)
            if start is None:
                raise CollectionError("The saved provider response declared no further pages")
            if type(start) is not int or start < 0:
                raise CollectionError("Saved pagination offset is invalid")
            if pages >= limit:
                raise CollectionError("Increase the total page budget to collect more")
    if fetcher == "scraperapi":
        if allow_paid is not True:
            reason = "Refresh requests new data." if refresh else ("Collect More requests additional pages." if resume_run_id is not None else "No sufficient completed collection is available.")
            raise PaidRequestRequired(f"{reason} Authorize up to {limit-pages} paid page request(s)?")
        get_scraper_config()
    if resume_run_id is None:
        with db.get_connection() as connection:
            try:
                query_id = db.insert_search_query(connection, query)
                run_id = db.insert_search_run(connection, query_id, engine, provider)
                connection.commit()
            except Exception:
                connection.rollback()
                raise SearchError("Could not create query/run records; check MySQL") from None
    else:
        run_id = resume_run_id
    observations = existing
    _, counts = clean_results(observations, preserve_urls=engine == "google")
    evidence = url_evidence_counts(observations)
    metadata = {"provider": provider, "fetcher": fetcher, "mode": mode, "target_count": target,
                "max_pages": limit, "pages": pages, "next_start": start, "stop_reason": "in_progress",
                "endpoint": "/structured/google/search/v1" if engine == "google" else "bing_html",
                "publisher_destinations_verified": False, "paid_authorized": allow_paid is True,
                "authorized_new_pages": limit-pages, **evidence}
    status, error, stop_reason = "completed", None, "page_budget"
    storage_error = False
    next_start = start
    try:
        directory = Path(__file__).resolve().parent / "artifacts" / f"run_{run_id}"
        directory.mkdir(parents=True, exist_ok=True)
        for page in range(pages, limit):
            path = directory / f"page_{page+1}.json"
            if path.exists():
                raise SearchError("Uncommitted page evidence already exists; inspect artifacts before requesting it again")
            rows, next_start = fetch_page(query, start)
            for row in rows:
                row["page_number"] = page + 1
            with path.open("x", encoding="utf-8") as output:
                json.dump({"organic_results": rows, "provider": provider, "start": start}, output, ensure_ascii=False)
            combined, new_counts = clean_results(observations + rows, preserve_urls=engine == "google")
            new_evidence = url_evidence_counts(combined)
            new_metadata = {**metadata, "pages": page+1, "next_start": next_start, **new_evidence}
            try:
                with db.get_connection() as connection:
                    try:
                        db.update_result_duplicates(connection, [r for r in combined[:len(observations)] if "id" in r])
                        db.insert_search_results(connection, run_id, combined[len(observations):])
                        db.update_search_run(connection, run_id, "running", new_counts)
                        db.update_collection_metadata(connection, run_id, new_metadata)
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
            except Exception:
                storage_error = True
                raise SearchError("Page storage failed and was rolled back; earlier committed pages retained") from None
            previous = counts["final_count"]
            observations, counts, evidence, metadata = combined, new_counts, new_evidence, new_metadata
            pages = page + 1
            if mode == "search": stop_reason = "one_page"; break
            if evidence["direct_url_count"] >= target: stop_reason = "target_reached"; break
            if not rows: stop_reason = "empty_page"; break
            if next_start is None: stop_reason = "provider_exhausted"; break
            if counts["final_count"] == previous: stop_reason = "no_unique_progress"; break
            start = next_start
            if page+1 < limit:
                time.sleep(2)
    except SearchError as failure:
        status, error, stop_reason = "failed", str(failure), "error"
    except Exception:
        status, error, stop_reason = "failed", "Response/artifact processing failed; inspect local evidence", "error"
    metadata = {**metadata, "pages": pages, "stop_reason": stop_reason, **evidence,
                "target_met": evidence["direct_url_count"] >= 50 if mode == "collect" else counts["final_count"] > 0}
    try:
        with db.get_connection() as connection:
            try:
                db.update_search_run(connection, run_id, status, counts, error)
                db.update_collection_metadata(connection, run_id, metadata)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except Exception:
        raise SearchError(f"Run {run_id}: could not save final collection status; committed pages remain available") from None
    if storage_error:
        raise SearchError(f"Run {run_id}: page storage failed and was rolled back; earlier committed pages retained")
    summary = {"run_id": run_id, "engine": engine, "provider": provider, "fetcher": fetcher,
               "status": status, "pages": pages, "reused": False, "target_count": target,
               **counts, **evidence, "error": error, "warning": None}
    if capture:
        summary["capture"] = capture_run(query, run_id, engine=engine) if status == "completed" and counts["final_count"] else {"status": "skipped", "error": "Capture skipped: no completed organic results"}
    return summary


def capture_run(query: str, run_id: int, engine: str = "bing") -> dict:
    """Keep capture failures separate from the already committed search results."""
    directory = Path(__file__).resolve().parent / "artifacts" / f"run_{run_id}" / f"capture_{uuid4().hex}"
    try:
        screenshot = capture_search_page(query, directory / "search_results.png", engine=engine)
    except (CaptureError, ImportError) as error:
        message = str(error) if isinstance(error, CaptureError) else "Playwright is missing; install project dependencies"
        return {"status": "failed", "error": message}
    ocr, error = None, None
    try:
        ocr = extract_screenshot_text(screenshot, directory / "ocr.txt")
    except (CaptureError, ImportError) as failure:
        error = str(failure) if isinstance(failure, CaptureError) else "OCR Python dependencies are missing; screenshot retained"
    try:
        with db.get_connection() as connection:
            try:
                artifact_id = db.insert_capture_artifact(connection, run_id, str(screenshot), str(ocr) if ocr else None)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except Exception:
        return {"status": "failed", "screenshot_path": str(screenshot), "ocr_text_path": str(ocr) if ocr else None,
                "error": "Capture metadata could not be saved; local files retained and search results unchanged"}
    return {"status": "completed" if ocr else "screenshot_only", "artifact_id": artifact_id,
            "screenshot_path": str(screenshot), "ocr_text_path": str(ocr) if ocr else None, "error": error}



def main() -> int:
    parser = argparse.ArgumentParser(description="Cache-first search or explicit 50-URL collection")
    parser.add_argument("query")
    parser.add_argument("--engine", choices=["google", "bing"], default="google")
    parser.add_argument("--max-pages", type=int, help="total collection budget, 1–20; default from COLLECTION_MAX_PAGES")
    parser.add_argument("--collect-50", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="deliberately bypass saved-result reuse")
    parser.add_argument("--resume-run", type=int, help="Collect More: append to this exact-query/provider run")
    parser.add_argument("--allow-paid", action="store_true", help="explicitly authorize requests within the selected page budget")
    parser.add_argument("--capture", action="store_true", help="explicit authentic provider-page capture/OCR")
    args = parser.parse_args()
    try:
        summary = run_search(args.query, args.max_pages, engine=args.engine, capture=args.capture,
                             mode="collect" if args.collect_50 else "search", refresh=args.refresh,
                             resume_run_id=args.resume_run, allow_paid=args.allow_paid)
    except (ValueError, SearchError) as error:
        print(error)
        return 1
    except Error:
        print("MySQL unavailable; check local configuration")
        return 1
    print(summary)
    print("50-URL requirement satisfied." if summary["final_count"] >= 50 else "50-URL requirement not yet satisfied.")
    return 0 if summary["status"] == "completed" and summary.get("capture", {}).get("status", "completed") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
