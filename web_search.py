"""Small web routes around the existing ETL and database read functions."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from mysql.connector import Error
from pydantic import BaseModel, Field, model_validator

import db
from google_search import SearchError
from run_search import run_search, validate_query

router = APIRouter()
ROOT = Path(__file__).resolve().parent
ARTIFACT_ROOT = ROOT / "artifacts"


class SearchRequest(BaseModel):
    """Explicit engine/fetcher choices; no environment-driven paid requests."""
    query: str = Field(min_length=1, max_length=1000)
    engine: Literal["google", "bing", "duckduckgo"] = "google"
    fetcher: Literal["direct", "scraperapi"] | None = None
    max_pages: int = Field(default=1, ge=1, le=5, strict=True)

    @model_validator(mode="after")
    def validate_search(self):
        validate_query(self.query)
        if self.fetcher is None:
            self.fetcher = "scraperapi" if self.engine == "google" else "direct"
        return self


def read_run(run_id: int) -> dict:
    """Serialize results and ID-based artifact links, without local filesystem paths."""
    data = db.get_search_run(run_id)
    if data is None:
        raise HTTPException(404, "Search run not found")
    # The schema predates fetcher tracking. Preserve new web-run choices in a small
    # local sidecar; older runs honestly show an unknown fetcher, without guessing.
    fetcher = None
    metadata = ARTIFACT_ROOT / f"run_{run_id}" / "web_request.json"
    try:
        if metadata.resolve().is_relative_to(ARTIFACT_ROOT.resolve()):
            candidate = json.loads(metadata.read_text(encoding="utf-8")).get("fetcher")
            if candidate in {"direct", "scraperapi"}:
                fetcher = candidate
    except (OSError, ValueError, AttributeError):
        pass
    data["run"]["fetcher"] = fetcher
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
                             fetcher=request.fetcher, capture=False)
        warning = None
        try:
            directory = ARTIFACT_ROOT / f"run_{summary['run_id']}"
            if not directory.resolve().is_relative_to(ARTIFACT_ROOT.resolve()):
                raise OSError("Invalid artifacts directory")
            directory.mkdir(parents=True, exist_ok=True)
            # Only non-secret provenance is saved, not keys or configuration dumps.
            with (directory / "web_request.json").open("x", encoding="utf-8") as output:
                json.dump({"fetcher": request.fetcher, "max_pages": request.max_pages, "pages": summary.get("pages")}, output)
        except OSError:
            warning = "Search saved; fetcher history metadata could not be saved"
        data = read_run(summary["run_id"])
        data["run"]["fetcher"] = request.fetcher
        data["warning"] = warning
        return data
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
