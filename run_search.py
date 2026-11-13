"""Command-line Google HTML → extraction → cleaning → MySQL workflow."""
import argparse
from pathlib import Path
import re
import time

from mysql.connector import Error

import db
from clean_urls import clean_results
from config import get_scraper_config, get_search_fetcher
from google_search import SearchError, fetch_direct_html, fetch_html
from parse_results import next_page_start, parse_results

FILLER_WORDS = {"a", "an", "the", "and", "or", "not", "of", "in", "on", "at", "to", "for", "with", "please"}


def validate_query(query: str) -> None:
    """Require five alphabetic word tokens excluding an explicit filler list."""
    words = re.findall(r"[^\W\d_]+", query.lower(), flags=re.UNICODE)
    if len(query) > 1000:
        raise ValueError("Query must contain at most 1000 characters")
    if sum(word not in FILLER_WORDS for word in words) < 5:
        raise ValueError("Query must contain at least five meaningful words (see README counting rule)")


def run_search(query: str, max_pages: int = 1, fetcher: str | None = None) -> dict:
    """Commit the run before retrieval, then atomically store observations and counts."""
    validate_query(query)
    if not 1 <= max_pages <= 5:
        raise ValueError("max_pages must be from 1 to 5")
    fetcher = get_search_fetcher() if fetcher is None else fetcher
    if fetcher not in {"direct", "scraperapi"}:
        raise ValueError("Fetcher must be direct or scraperapi")
    if fetcher == "scraperapi":
        get_scraper_config()
    retrieve = fetch_direct_html if fetcher == "direct" else fetch_html
    with db.get_connection() as connection:
        try:
            query_id = db.insert_search_query(connection, query)
            run_id = db.insert_search_run(connection, query_id)
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
            html = retrieve(query, start=start)
            (directory / f"page_{page + 1}.html").write_text(html, encoding="utf-8")
            rows = parse_results(html)
            for row in rows:
                row["result_rank"] += len(observations)
            observations.extend(rows)
            pages += 1
            _, counts = clean_results(observations)
            if counts["final_count"] >= 50:
                break
            next_start = next_page_start(html, query, start)
            if next_start is None:
                break
            start = next_start
            if page + 1 < max_pages:
                time.sleep(2)
    except SearchError as failure:
        status, error = "failed", str(failure)
    except Exception:
        status, error = "failed", "HTML processing failed; inspect local artifacts and configuration"
    results, counts = clean_results(observations)
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
    return {"run_id": run_id, "fetcher": fetcher, "status": status, "pages": pages, **counts, "error": error}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one small Google HTML search ETL")
    parser.add_argument("query")
    parser.add_argument("--max-pages", type=int, default=1, choices=range(1, 6),
                        help="default 1; up to 5 pages after confirming HTML extraction works")
    parser.add_argument("--fetcher", choices=["direct", "scraperapi"],
                        help="overrides SEARCH_FETCHER; otherwise defaults to direct")
    args = parser.parse_args()
    try:
        summary = run_search(args.query, args.max_pages, args.fetcher)
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
    print(f"Run {summary['run_id']}: {summary['status']}; fetcher={summary['fetcher']}; parsed pages={summary['pages']}; "
          f"raw={summary['raw_count']}, ads={summary['ad_count']}, "
          f"duplicates={summary['duplicate_count']}, final={summary['final_count']}")
    if summary["error"]:
        print(summary["error"])
    print("50 unique organic results achieved." if summary["final_count"] >= 50
          else "50 unique organic results have not been achieved.")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
