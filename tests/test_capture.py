"""Mock browser/OCR/database handling without real navigation or MySQL writes."""
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlencode

from PIL import Image
import pytest
import pytesseract
import playwright.sync_api

import db
import run_search
from capture_page import CaptureError, capture_search_page
from ocr_capture import extract_screenshot_text

QUERY = "childhood cancer early diagnosis methods"


@pytest.fixture
def browser(monkeypatch):
    manager = MagicMock()
    chromium = manager.__enter__.return_value.chromium
    instance = chromium.launch.return_value
    page = instance.new_page.return_value
    page.url = "https://www.bing.com/search?" + urlencode({"q": QUERY})
    page.goto.return_value.status = 200
    page.locator.return_value.count.return_value = 0
    page.locator.return_value.inner_text.return_value = "Fixture search results"
    def screenshot(**kwargs):
        Image.new("RGB", (100, 100), "white").save(kwargs["path"])
    page.screenshot.side_effect = screenshot
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: manager)
    return page, instance


def test_screenshot_file_and_browser_cleanup(browser, tmp_path):
    page, instance = browser
    destination = tmp_path / "capture" / "results.png"
    assert capture_search_page(QUERY, destination) == destination.resolve()
    assert destination.stat().st_size > 0
    assert page.screenshot.call_args.kwargs["full_page"] is True
    assert urlencode({"q": QUERY}) in page.goto.call_args.args[0]
    instance.close.assert_called_once()


@pytest.mark.parametrize("failure", ["http", "challenge", "no_results", "wrong_query", "browser"])
def test_capture_failures_do_not_save(browser, tmp_path, failure):
    page, instance = browser
    if failure == "http":
        page.goto.return_value.status = 403
    elif failure == "challenge":
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.first.is_visible.return_value = True
    elif failure == "no_results":
        page.locator.return_value.first.wait_for.side_effect = playwright.sync_api.TimeoutError("sensitive detail")
    elif failure == "wrong_query":
        page.url = "https://www.bing.com/search?q=wrong"
    else:
        page.screenshot.side_effect = playwright.sync_api.Error("sensitive detail")
    with pytest.raises(CaptureError) as error:
        capture_search_page(QUERY, tmp_path / "result.png")
    assert "sensitive detail" not in str(error.value)
    assert not (tmp_path / "result.png").exists()
    instance.close.assert_called_once()


def test_screenshot_refuses_overwrite(tmp_path):
    destination = tmp_path / "results.png"
    destination.write_bytes(b"existing")
    with pytest.raises(CaptureError, match="overwrite"):
        capture_search_page(QUERY, destination)
    assert destination.read_bytes() == b"existing"


def test_ocr_utf8_file(monkeypatch, tmp_path):
    image = tmp_path / "results.png"
    Image.new("RGB", (100, 100)).save(image)
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *args, **kwargs: "Fixture OCR — diagnosis\n")
    destination = tmp_path / "ocr.txt"
    assert extract_screenshot_text(image, destination) == destination.resolve()
    assert destination.read_text(encoding="utf-8") == "Fixture OCR — diagnosis\n"
    with pytest.raises(CaptureError, match="overwrite"):
        extract_screenshot_text(image, destination)


@pytest.mark.parametrize("failure", ["missing", "timeout", "empty"])
def test_ocr_failure_preserves_screenshot(monkeypatch, tmp_path, failure):
    image = tmp_path / "results.png"
    Image.new("RGB", (100, 100)).save(image)
    def ocr(*args, **kwargs):
        if failure == "missing":
            raise pytesseract.TesseractNotFoundError()
        if failure == "timeout":
            raise RuntimeError("sensitive detail")
        return " "
    monkeypatch.setattr(pytesseract, "image_to_string", ocr)
    with pytest.raises(CaptureError) as error:
        extract_screenshot_text(image, tmp_path / "ocr.txt")
    assert "sensitive detail" not in str(error.value)
    assert image.exists() and not (tmp_path / "ocr.txt").exists()


@pytest.fixture
def capture_workflow(monkeypatch, tmp_path):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    insert = MagicMock(return_value=40)
    monkeypatch.setattr(db, "insert_capture_artifact", insert)
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    def screenshot(query, destination):
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"mock screenshot")
        return destination
    def ocr(screenshot, destination):
        destination.write_text("Fixture OCR", encoding="utf-8")
        return destination
    monkeypatch.setattr(run_search, "capture_search_page", screenshot)
    monkeypatch.setattr(run_search, "extract_screenshot_text", ocr)
    return connection, insert


def test_capture_path_persistence_and_unique_names(capture_workflow):
    connection, insert = capture_workflow
    summary = run_search.capture_run(QUERY, 12)
    assert summary["status"] == "completed" and summary["artifact_id"] == 40
    assert insert.call_args.args[1] == 12
    assert Path(insert.call_args.args[2]).is_file()
    assert Path(insert.call_args.args[3]).is_file()
    assert "run_12" in summary["screenshot_path"]
    second = run_search.capture_run(QUERY, 12)
    assert second["screenshot_path"] != summary["screenshot_path"]
    assert connection.commit.call_count == 2


def test_capture_partial_ocr_failure(capture_workflow, monkeypatch):
    def fail(*args):
        raise CaptureError("Tesseract unavailable")
    monkeypatch.setattr(run_search, "extract_screenshot_text", fail)
    summary = run_search.capture_run(QUERY, 12)
    assert summary["status"] == "screenshot_only"
    assert summary["ocr_text_path"] is None
    assert capture_workflow[1].call_args.args[3] is None
    capture_workflow[0].commit.assert_called_once()


def test_screenshot_failure_has_no_metadata(capture_workflow, monkeypatch):
    def fail(*args):
        raise CaptureError("Browser unavailable")
    monkeypatch.setattr(run_search, "capture_search_page", fail)
    summary = run_search.capture_run(QUERY, 12)
    assert summary == {"status": "failed", "error": "Browser unavailable"}
    capture_workflow[1].assert_not_called()


def test_capture_database_rollback_leaves_files(capture_workflow):
    connection, insert = capture_workflow
    insert.side_effect = RuntimeError("password")
    summary = run_search.capture_run(QUERY, 12)
    assert summary["status"] == "failed"
    assert Path(summary["screenshot_path"]).is_file()
    assert Path(summary["ocr_text_path"]).is_file()
    assert "password" not in summary["error"]
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()


def test_capture_sql_parameters():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.lastrowid = 30
    assert db.insert_capture_artifact(connection, 12, "/tmp/image.png", None) == 30
    assert cursor.execute.call_args.args[1] == (12, "/tmp/image.png", None)
    assert "%s" in cursor.execute.call_args.args[0]


def test_capture_unsupported_engine_before_writes():
    with pytest.raises(ValueError, match="Bing only"):
        run_search.run_search(QUERY, engine="google", capture=True)


@pytest.mark.parametrize("capture,search_fails", [(False, False), (True, False), (True, True)])
def test_optional_capture_is_after_etl_commit(monkeypatch, tmp_path, capture, search_fails):
    import bing_search
    from google_search import SearchError
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db, "insert_search_query", lambda *args: 10)
    monkeypatch.setattr(db, "insert_search_run", lambda *args: 20)
    monkeypatch.setattr(db, "insert_search_results", MagicMock())
    update = MagicMock()
    monkeypatch.setattr(db, "update_search_run", update)
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    def fetch(*args, **kwargs):
        if search_fails:
            raise SearchError("Bing unavailable")
        return (Path(__file__).parent / "fixtures" / "bing_results.html").read_text()
    monkeypatch.setattr(bing_search, "fetch_html", fetch)
    def capture_files(query, run_id):
        assert connection.commit.call_count == 2
        assert query == QUERY and run_id == 20
        return {"status": "failed", "error": "Fixture browser failure"}
    capture_call = MagicMock(side_effect=capture_files)
    monkeypatch.setattr(run_search, "capture_run", capture_call)
    summary = run_search.run_search(QUERY, engine="bing", capture=capture)
    if capture and not search_fails:
        capture_call.assert_called_once()
        assert summary["status"] == "completed"
        assert summary["capture"]["status"] == "failed"
        assert update.call_args.args[2] == "completed"
    else:
        capture_call.assert_not_called()
    if capture and search_fails:
        assert summary["capture"]["status"] == "skipped"
    if not capture:
        assert "capture" not in summary


@pytest.mark.parametrize("query", ["childhood cancer early diagnosis methods", "b) Childhood cancer early diagnosis methods"])
def test_capture_preserves_exact_query_including_assignment_prefix(browser, tmp_path, query):
    from urllib.parse import parse_qs, urlsplit
    page, instance = browser
    page.url = "https://www.bing.com/search?" + urlencode({"q": query})
    capture_search_page(query, tmp_path / "result.png")
    actual_url = page.goto.call_args.args[0]
    assert parse_qs(urlsplit(actual_url).query)["q"] == [query]
    if query.startswith("b)"):
        assert "b%29+Childhood" in actual_url
