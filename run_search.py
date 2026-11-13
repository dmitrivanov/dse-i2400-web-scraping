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
from clean_urls import clean_results
from config import get_collection_page_limit, get_scraper_config
from google_search import SearchError
from saved_searches import find_saved_collection, provider_for_run, read_metadata
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


def run_search(query: str, max_pages: int | None = None, fetcher: str | None = None,
               engine: str = "google", capture: bool = False, mode: str = "search",
               refresh: bool = False, resume_run_id: int | None = None) -> dict:
    """Reuse adequate saved data before any paid call; deliberate actions can refresh/extend."""
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
    if capture and engine != "bing":
        raise CollectionError("Screenshot capture currently supports Bing only")
    if resume_run_id is not None and (mode != "collect" or refresh):
        raise CollectionError("Collect More requires collect mode without refresh")
    if not refresh and resume_run_id is None:
        saved = find_saved_collection(query, engine, provider, target)
        if saved:
            run = saved["run"]
            summary = {"run_id": run["id"], "engine": engine, "provider": provider, "fetcher": fetcher,
                       "status": run["status"], "pages": 0, "reused": True, "target_count": target,
                       **{name: run[name] for name in ("raw_count", "ad_count", "duplicate_count", "final_count")}, "error": None}
            if capture:
                summary["capture"] = capture_run(query, run["id"])
            return summary
    existing = []
    start, completed_pages = 0, 0
    if resume_run_id is not None:
        data = db.get_search_run(resume_run_id)
        if (not data or data["run"]["query_text"] != query or data["run"]["engine"] != engine
                or provider_for_run(data["run"]) != provider or data["run"]["status"] not in {"completed", "failed"}):
            raise CollectionError("Collect More requires a matching saved query/provider and a finished run")
        existing = data["results"]
        _, existing_counts = clean_results(existing, preserve_urls=engine == "google")
        if data["run"]["status"] == "completed" and existing_counts["final_count"] >= target:
            return {"run_id": resume_run_id, "engine": engine, "provider": provider,
                    "fetcher": fetcher, "status": "completed", "pages": 0, "reused": True,
                    "target_count": target, **existing_counts, "error": None}
        meta = read_metadata(resume_run_id)
        if not meta:
            meta = read_metadata(resume_run_id, "web_request.json")
        completed_pages = meta.get("pages")
        if type(completed_pages) is not int or completed_pages < 1:
            raise CollectionError("Saved page provenance is unavailable; use Refresh to start a new collection")
        start = meta.get("next_start", completed_pages * 10 if engine == "google" else None)
        if start is None:
            raise CollectionError("The saved provider response declared no further pages")
        if type(start) is not int or start < 0:
            raise CollectionError("Saved pagination offset is invalid")
        if completed_pages >= limit:
            raise CollectionError("Increase the total page budget to collect more")
        run_id = resume_run_id
    if fetcher == "scraperapi":
        get_scraper_config()  # Only after cache/provenance checks; cached reads need no key.
    if resume_run_id is None:
        with db.get_connection() as connection:
            try:
                query_id = db.insert_search_query(connection, query)
                run_id = db.insert_search_run(connection, query_id, engine, provider)
                connection.commit()
            except Exception:
                connection.rollback()
                raise SearchError("Could not create query/run records; check MySQL") from None
    observations = list(existing)
    status, error = "completed", None
    pages = completed_pages
    next_start = start
    try:
        directory = Path(__file__).resolve().parent / "artifacts" / f"run_{run_id}"
        directory.mkdir(parents=True, exist_ok=True)
        for page in range(completed_pages, limit):
            if (directory / f"page_{page + 1}.json").exists():
                raise SearchError("Uncommitted page evidence already exists; inspect artifacts before requesting it again")
            rows, next_start = fetch_page(query, start)
            for row in rows:
                row["page_number"] = page + 1
            with (directory / f"page_{page + 1}.json").open("x", encoding="utf-8") as output:
                json.dump({"organic_results": rows, "provider": provider, "start": start}, output, ensure_ascii=False)
            previous = clean_results(observations, preserve_urls=engine == "google")[1]["final_count"]
            observations.extend(rows)
            pages += 1
            _, counts = clean_results(observations, preserve_urls=engine == "google")
            if mode == "search" or counts["final_count"] >= target or next_start is None or not rows:
                break
            # Repeated pages cannot safely be treated as fresh progress.
            if counts["final_count"] == previous:
                break
            start = next_start
            if page + 1 < limit:
                time.sleep(2)
    except SearchError as failure:
        status, error = "failed", str(failure)
    except Exception:
        status, error = "failed", "Response/artifact processing failed; inspect local evidence"
    results, counts = clean_results(observations, preserve_urls=engine == "google")
    try:
        with db.get_connection() as connection:
            try:
                db.update_result_duplicates(connection, results[:len(existing)])
                db.insert_search_results(connection, run_id, results[len(existing):])
                db.update_search_run(connection, run_id, status, counts, error)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except Exception:
        # A new run needs a durable failed status; a resumed collection retains its
        # previous committed state/counts when the append transaction rolls back.
        if not existing:
            try:
                with db.get_connection() as connection:
                    try:
                        db.update_search_run(connection, run_id, "failed", dict.fromkeys(counts, 0), "Result storage failed; no new rows committed")
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise
            except Exception:
                raise SearchError(f"Run {run_id}: storage and failure-status update failed; inspect Workbench") from None
        raise SearchError(f"Run {run_id}: result storage failed and was rolled back") from None
    warning = None
    try:
        metadata = {"provider": provider, "fetcher": fetcher, "mode": mode, "target_count": target,
                    "max_pages": limit, "pages": pages, "next_start": next_start}
        temporary = directory / "collection.tmp"
        temporary.write_text(json.dumps(metadata), encoding="utf-8")
        temporary.replace(directory / "collection.json")
    except OSError:
        warning = "Search data saved; collection metadata could not be saved"
    summary = {"run_id": run_id, "engine": engine, "provider": provider, "fetcher": fetcher,
               "status": status, "pages": pages, "reused": False, "target_count": target,
               **counts, "error": error, "warning": warning}
    if capture:
        summary["capture"] = capture_run(query, run_id) if status == "completed" and counts["final_count"] else {"status": "skipped", "error": "Capture skipped: no completed organic results"}
    return summary


def capture_run(query: str, run_id: int) -> dict:
    """Keep capture failures separate from the already committed search results."""
    directory = Path(__file__).resolve().parent / "artifacts" / f"run_{run_id}" / f"capture_{uuid4().hex}"
    try:
        screenshot = capture_search_page(query, directory / "search_results.png")
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
    parser.add_argument("--capture", action="store_true", help="optional authentic Bing capture/OCR only")
    args = parser.parse_args()
    try:
        summary = run_search(args.query, args.max_pages, engine=args.engine, capture=args.capture,
                             mode="collect" if args.collect_50 else "search", refresh=args.refresh,
                             resume_run_id=args.resume_run)
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
