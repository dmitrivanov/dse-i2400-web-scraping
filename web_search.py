"""Small web routes around the existing ETL and database read functions."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from mysql.connector import Error
from pydantic import BaseModel, Field, model_validator

import db
from google_search import SearchError
from run_search import CollectionError, PaidRequestRequired, capture_run, run_search, validate_query
from config import get_collection_page_limit
from saved_searches import provider_for_run, collection_metadata_for_run

router = APIRouter()
ROOT = Path(__file__).resolve().parent
ARTIFACT_ROOT = ROOT / "artifacts"


class SearchRequest(BaseModel):
    """Primary provider and deliberate collection/refresh choices, without fallback."""
    query: str = Field(min_length=1, max_length=1000)
    engine: Literal["google"] = "google"
    fetcher: Literal["scraperapi"] = "scraperapi"
    mode: Literal["search", "collect"] = "search"
    max_pages: int | None = Field(default=None, ge=1, le=20, strict=True)
    refresh: bool = False
    allow_paid: bool = Field(default=False, strict=True)
    resume_run_id: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def validate_search(self):
        validate_query(self.query)
        if self.mode == "search":
            if self.max_pages not in (None, 1):
                raise ValueError("Normal search uses one page; choose Collect 50 for pagination")
            self.max_pages = 1
        elif self.max_pages is None:
            self.max_pages = get_collection_page_limit()
        if self.resume_run_id is not None and (self.mode != "collect" or self.refresh):
            raise ValueError("Collect More requires collect mode without refresh")
        return self


def read_run(run_id: int) -> dict:
    """Serialize results and ID-based artifact links, without local filesystem paths."""
    data = db.get_search_run(run_id)
    if data is None:
        raise HTTPException(404, "Search run not found")
    # Old web sidecars are read for history, not written by new search requests.
    collection = collection_metadata_for_run(data["run"])
    legacy = collection
    candidate = legacy.get("fetcher")
    fetcher = candidate if candidate in {"direct", "scraperapi"} else None
    data["run"]["provider"] = provider_for_run(data["run"])
    data["run"]["fetcher"] = "scraperapi" if data["run"]["provider"] == "google:scraperapi:structured" else fetcher
    from clean_urls import clean_results, is_google_redirect, url_evidence_counts
    cleaned, _ = clean_results(data["results"], preserve_urls=data["run"]["engine"] == "google")
    for row in data["results"]:
        row["destination_unverified"] = is_google_redirect(row.get("normalized_url") or row["original_url"])
    evidence = url_evidence_counts(cleaned)
    data["run"].update(evidence)
    data["run"]["satisfies_50"] = evidence["direct_url_count"] >= 50
    data["collection"] = collection
    data["artifacts"] = [
        {"id": item["id"],
         "screenshot_url": f"/api/artifacts/{item['id']}/screenshot" if item["screenshot_path"] else None,
         "ocr_url": f"/api/artifacts/{item['id']}/ocr" if item["ocr_text_path"] else None}
        for item in data["artifacts"]
    ]
    return data


@router.get("/search", include_in_schema=False)
def search_page():
    return FileResponse(ROOT / "static" / "index.html")


@router.post("/api/search")
def execute_search(request: SearchRequest):
    """Run a bounded number of pages in FastAPI's sync worker, then read persisted rows."""
    try:
        summary = run_search(request.query, max_pages=request.max_pages, engine=request.engine,
                             fetcher=request.fetcher, capture=False, mode=request.mode,
                             refresh=request.refresh, resume_run_id=request.resume_run_id, allow_paid=request.allow_paid)
        data = read_run(summary["run_id"])
        data["run"]["fetcher"] = request.fetcher
        data["reused"] = summary.get("reused", False)
        data["target_count"] = summary.get("target_count", 1)
        data["warning"] = summary.get("warning")
        return data
    except PaidRequestRequired as error:
        raise HTTPException(409, {"requires_confirmation": True, "message": str(error)}) from None
    except CollectionError as error:
        raise HTTPException(400, str(error)) from None
    except ValueError:
        raise HTTPException(400, "Search configuration is invalid; check local settings") from None
    except Error:
        raise HTTPException(503, "Database unavailable; check local MySQL configuration") from None
    except SearchError:
        raise HTTPException(502, "Search could not be completed; inspect recent runs for its saved status") from None


@router.get("/api/runs")
def recent_runs():
    try:
        return db.get_recent_search_runs()
    except (Error, ValueError):
        raise HTTPException(503, "Database unavailable; check local MySQL configuration") from None


@router.get("/api/runs/{run_id}")
def previous_run(run_id: int):
    if run_id < 1:
        raise HTTPException(422, "Run ID must be positive")
    try:
        return read_run(run_id)
    except (Error, ValueError):
        raise HTTPException(503, "Database unavailable; check local MySQL configuration") from None


@router.get("/api/artifacts/{artifact_id}/{kind}")
def artifact_file(artifact_id: int, kind: Literal["screenshot", "ocr"]):
    try:
        item = db.get_capture_artifact(artifact_id)
    except (Error, ValueError):
        raise HTTPException(503, "Database unavailable") from None
    if item is None:
        raise HTTPException(404, "Artifact not found")
    value = item["screenshot_path" if kind == "screenshot" else "ocr_text_path"]
    if not value:
        raise HTTPException(404, "Artifact file not available")
    try:
        path = Path(value).resolve()
        expected = ".png" if kind == "screenshot" else ".txt"
        if not path.is_relative_to(ARTIFACT_ROOT.resolve()) or path.suffix != expected or not path.is_file():
            raise HTTPException(404, "Artifact file not available")
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(404, "Artifact file not available") from None
    return FileResponse(path, media_type="image/png" if kind == "screenshot" else "text/plain; charset=utf-8",
                        headers={"X-Content-Type-Options": "nosniff"})


@router.get("/api/search-options")
def search_options():
    try:
        return {"collection_max_pages": get_collection_page_limit(), "max_allowed_pages": 20}
    except ValueError:
        raise HTTPException(400, "Collection page configuration is invalid") from None


@router.post("/api/runs/{run_id}/capture")
def capture_saved_run(run_id: int):
    """Explicit browser/OCR action on the saved query, independent of paid search."""
    try:
        data = db.get_search_run(run_id)
        if not data:
            raise HTTPException(404, "Search run not found")
        run = data["run"]
        if run["engine"] not in {"google", "bing"} or run["status"] == "running" or not data["results"]:
            raise HTTPException(400, "Select a finished Google/Bing run with saved results to capture")
        result = capture_run(run["query_text"], run_id, engine=run["engine"])
        return {key: result[key] for key in ("status", "artifact_id", "error") if key in result}
    except (Error, ValueError):
        raise HTTPException(503, "Database unavailable; capture was not started") from None
