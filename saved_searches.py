"""Recognize provider provenance and reuse one exact-query saved collection."""
import json
from pathlib import Path

import db
from clean_urls import clean_results

ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts"


def read_metadata(run_id: int, filename: str = "collection.json") -> dict:
    """Read only controlled per-run metadata; missing historical metadata is normal."""
    try:
        path = ARTIFACT_ROOT / f"run_{run_id}" / filename
        if not path.resolve().is_relative_to(ARTIFACT_ROOT.resolve()):
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, RuntimeError):
        return {}


def provider_for_run(run: dict) -> str | None:
    """Historical Google JSON evidence can identify pre-provider-column runs."""
    if run.get("provider"):
        return run["provider"]
    if run["engine"] == "google":
        data = read_metadata(run["id"], "page_1.json")
        rows = data.get("organic_results")
        if isinstance(rows, list) and rows and all(isinstance(row, dict) and "original_url" in row for row in rows):
            return "google:scraperapi:structured"
    return None


def find_saved_collection(query: str, engine: str, provider: str, minimum_count: int) -> dict | None:
    """Return an adequate completed collection; never aggregate unrelated runs."""
    for run in db.get_collection_candidates(query, engine, minimum_count):
        if provider_for_run(run) != provider:
            continue
        data = db.get_search_run(run["id"])
        if data is None or data["run"]["query_text"] != query or data["run"]["engine"] != engine:
            continue
        _, counts = clean_results(data["results"], preserve_urls=engine == "google")
        # Offer adequate saved observations before considering any further spend.
        # The response separately reports opaque redirects and destination uncertainty.
        if counts["final_count"] >= minimum_count:
            return data
    return None


def collection_metadata_for_run(run: dict) -> dict:
    """MySQL is authoritative for new runs; old sidecars remain readable evidence."""
    value = run.get("collection_metadata")
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    return read_metadata(run["id"]) or read_metadata(run["id"], "web_request.json")
