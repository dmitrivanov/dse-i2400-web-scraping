"""Command-line search retrieval → extraction → cleaning → MySQL workflow."""
import argparse
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from mysql.connector import Error

import db
import bing_search
import duckduckgo_search
from capture_page import CaptureError, capture_search_page
from ocr_capture import extract_screenshot_text
from clean_urls import clean_results
from config import get_scraper_config, get_search_fetcher
from google_search import (
    SearchError, fetch_direct_html, fetch_results, parse_organic_results, next_results_start,
)
from parse_results import next_page_start, parse_results

FILLER_WORDS = {"a", "an", "the", "and", "or", "not", "of", "in", "on", "at", "to", "for", "with", "please"}


def validate_query(query: str) -> None:
    """Require five alphabetic word tokens excluding an explicit filler list."""
    words = re.findall(r"[^\W\d_]+", query.lower(), flags=re.UNICODE)
    if len(query) > 1000:
        raise ValueError("Query must contain at most 1000 characters")
    if sum(word not in FILLER_WORDS for word in words) < 5:
        raise ValueError("Query must contain at least five meaningful words (see README counting rule)")


def run_search(query: str, max_pages: int = 1, fetcher: str | None = None, engine: str = "google", capture: bool = False) -> dict:
    """Commit the run before retrieval, then atomically store observations and counts."""
    validate_query(query)
    if not 1 <= max_pages <= 5:
        raise ValueError("max_pages must be from 1 to 5")
    if engine not in {"google", "bing", "duckduckgo"}:
        raise ValueError("Engine must be google, bing, or duckduckgo")
    if capture and engine != "bing":
        raise ValueError("Screenshot capture currently supports Bing only")
    if fetcher is None:
        fetcher = get_search_fetcher() if engine == "google" else "direct"
    if fetcher not in {"direct", "scraperapi"}:
        raise ValueError("Fetcher must be direct or scraperapi")
    if fetcher == "scraperapi":
        get_scraper_config()
    retrieve = fetch_direct_html
    parse, next_page = parse_results, next_page_start
    if engine == "bing":
        retrieve, parse, next_page = bing_search.fetch_html, bing_search.parse_results, bing_search.next_page_start
    elif engine == "duckduckgo":
        retrieve, parse, next_page = duckduckgo_search.fetch_html, duckduckgo_search.parse_results, duckduckgo_search.next_page_start
    if fetcher == "scraperapi" and engine == "bing":
        retrieve = bing_search.fetch_scraper_html
    elif fetcher == "scraperapi" and engine == "duckduckgo":
        retrieve = duckduckgo_search.fetch_scraper_html
    structured = engine == "google" and fetcher == "scraperapi"
    if structured:
        retrieve = fetch_results
    with db.get_connection() as connection:
        try:
            query_id = db.insert_search_query(connection, query)
            run_id = db.insert_search_run(connection, query_id, engine)
            connection.commit()
        except Exception:
            connection.rollback()
            raise SearchError("Could not create query/run records; check MySQL") from None
    observations = []
    status, error = "completed", None
    pages = 0
    try:
        directory = Path(__file__).resolve().parent / "artifacts" / f"run_{run_id}"
        directory.mkdir(parents=True, exist_ok=True)
        start = 0
        for page in range(max_pages):
            payload = retrieve(query, start=start)
            if structured:
                rows = parse_organic_results(payload)
                # Save observations only; full provider metadata can contain signed URLs/keys.
                (directory / f"page_{page + 1}.json").write_text(
                    json.dumps({"organic_results": rows}, ensure_ascii=False), encoding="utf-8")
            else:
                (directory / f"page_{page + 1}.html").write_text(payload, encoding="utf-8")
                rows = parse(payload)
                for row in rows:
                    if row["result_rank"] is not None:
                        row["result_rank"] += len(observations)
            previous_final = clean_results(observations, preserve_urls=structured)[1]["final_count"]
            observations.extend(rows)
            pages += 1
            _, counts = clean_results(observations, preserve_urls=structured)
            if counts["final_count"] >= 50:
                break
            if structured and page > 0 and counts["final_count"] == previous_final:
                break
            next_start = next_results_start(payload, start) if structured else next_page(payload, query, start)
            if next_start is None:
                break
            start = next_start
            if page + 1 < max_pages:
                time.sleep(2)
    except SearchError as failure:
        status, error = "failed", str(failure)
    except Exception:
        status, error = "failed", "Search response processing failed; inspect local artifacts and configuration"
    results, counts = clean_results(observations, preserve_urls=structured)
    try:
        with db.get_connection() as connection:
            try:
                db.insert_search_results(connection, run_id, results)
                db.update_search_run(connection, run_id, status, counts, error)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    except Exception:
        # The result transaction rolled back. Persist a failure with zero stored rows.
        try:
            with db.get_connection() as connection:
                try:
                    zero = dict.fromkeys(counts, 0)
                    db.update_search_run(connection, run_id, "failed", zero,
                                         "Result storage failed; no result rows committed")
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        except Exception:
            raise SearchError(f"Run {run_id}: storage failed and failure status could not be saved; inspect Workbench") from None
        raise SearchError(f"Run {run_id}: result storage failed and was rolled back") from None
    summary = {"run_id": run_id, "engine": engine, "fetcher": fetcher, "status": status, "pages": pages, **counts, "error": error}
    if capture:
        if status == "completed" and counts["final_count"] > 0:
            summary["capture"] = capture_run(query, run_id)
        else:
            summary["capture"] = {"status": "skipped", "error": "Capture skipped because search ETL did not produce valid organic results"}
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
    parser = argparse.ArgumentParser(description="Run one small search HTML ETL")
    parser.add_argument("query")
    parser.add_argument("--max-pages", type=int, default=1, choices=range(1, 6),
                        help="explicit request budget: default 1 page, maximum 5")
    parser.add_argument("--fetcher", choices=["direct", "scraperapi"],
                        help="Google defaults to structured ScraperAPI; direct HTTP remains selectable")
    parser.add_argument("--engine", choices=["google", "bing", "duckduckgo"], default="google")
    parser.add_argument("--capture", action="store_true", help="Bing only: render first page, save screenshot and local OCR")
    args = parser.parse_args()
    try:
        summary = run_search(args.query, args.max_pages, args.fetcher, args.engine, args.capture)
    except ValueError as error:
        # Configuration and query validators only return static, credential-free messages.
        print(str(error))
        return 1
    except Error:
        print("MySQL unavailable; check local configuration and database access.")
        return 1
    except SearchError as error:
        print(error)
        return 1
    print(f"Run {summary['run_id']}: {summary['status']}; engine={summary['engine']}; fetcher={summary['fetcher']}; parsed pages={summary['pages']}; "
          f"raw={summary['raw_count']}, ads={summary['ad_count']}, "
          f"duplicates={summary['duplicate_count']}, final={summary['final_count']}")
    if summary["error"]:
        print(summary["error"])
    print("50 unique organic results achieved." if summary["final_count"] >= 50
          else "50 unique organic results have not been achieved.")
    if "capture" in summary:
        print("Capture:", summary["capture"])
        if summary["capture"]["status"] != "completed":
            return 1
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
