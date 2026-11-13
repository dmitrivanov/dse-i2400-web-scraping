from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

import db
import google_search
import run_search
from clean_urls import clean_results, normalize_url
from google_search import SearchError
from parse_results import parse_results

FIXTURES = Path(__file__).parent / "fixtures"


def sample():
    return (FIXTURES / "results.html").read_text()


def test_parser_and_counts():
    rows = parse_results(sample())
    assert len(rows) == 5
    assert [row["is_ad"] for row in rows] == [True, False, False, False, None]
    assert rows[1]["snippet"] == "Fixture snippet"
    assert rows[2]["snippet"] is None
    assert rows[2]["original_url"].startswith("/url?")
    cleaned, counts = clean_results(rows)
    assert counts == {"raw_count": 5, "ad_count": 1, "duplicate_count": 1, "final_count": 1}
    assert cleaned[2]["is_duplicate"] is True
    assert cleaned[3]["normalized_url"] is None
    assert cleaned[4]["is_ad"] is None


@pytest.mark.parametrize("html", ["", '<form action="/sorry/index"></form>',
    '<title>Before you continue to Google</title>', (FIXTURES / "changed.html").read_text()])
def test_unusable_pages(html):
    with pytest.raises(SearchError):
        parse_results(html)


@pytest.mark.parametrize("original, expected", [
    ("HTTPS://Example.COM:443/a?utm_source=x&ID=%2f#part", "https://example.com/a?ID=%2f#part"),
    ("https://example.com/?a=1&a=2&fbclid=x", "https://example.com/?a=1&a=2"),
    ("//EXAMPLE.com/a", "https://example.com/a"),
    ("/url?q=https%3A%2F%2Fexample.com%2Fa", "https://example.com/a"),
    ("https://example.com/a/../b", "https://example.com/a/../b"),
    ("javascript:alert(1)", None), ("https://u:p@example.com", None),
    ("https://example.com:bad/", None), ("https://example.com/a b", None),
    ("/search?q=example", None), ("", None),
])
def test_normalization(original, expected):
    assert normalize_url(original) == expected


def test_ad_and_unknown_do_not_claim_organic_url():
    rows = [{"original_url": "https://example.com", "is_ad": flag} for flag in [True, None, False, False]]
    _, counts = clean_results(rows)
    assert counts == {"raw_count": 4, "ad_count": 1, "duplicate_count": 3, "final_count": 1}


@pytest.mark.parametrize("query", ["childhood cancer early diagnosis methods", "the childhood cancer early diagnosis methods AND care"])
def test_valid_query(query):
    run_search.validate_query(query)


@pytest.mark.parametrize("query", ["", "the and OR not please", "childhood cancer diagnosis methods", "x" * 1001])
def test_invalid_query(query):
    with pytest.raises(ValueError):
        run_search.validate_query(query)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(google_search, "get_scraper_config", lambda: {"api_key": "test-secret", "base_url": "https://api.scraperapi.com"})


@pytest.mark.parametrize("status, body", [(401, "test-secret"), (500, "error"), (200, " ")])
def test_provider_bad_response(provider, monkeypatch, status, body):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(status, text=body))
    with pytest.raises(SearchError) as error:
        google_search.fetch_html("query")
    assert "test-secret" not in str(error.value)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("test-secret"), httpx.ConnectError("test-secret")])
def test_provider_network_failure(provider, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(SearchError) as error:
        google_search.fetch_html("query")
    assert "test-secret" not in str(error.value)


def test_provider_parameters_and_sanitizing(provider, monkeypatch):
    def respond(url, **kwargs):
        assert kwargs["params"]["url"].startswith("https://www.google.com/search?")
        assert "start=10" in kwargs["params"]["url"]
        assert kwargs["follow_redirects"] is False
        return httpx.Response(200, text="<html>test-secret</html>")
    monkeypatch.setattr(httpx, "get", respond)
    assert "test-secret" not in google_search.fetch_html("five words in a query", 10)


@pytest.fixture
def workflow(monkeypatch, tmp_path):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db, "insert_search_query", lambda *args: 10)
    monkeypatch.setattr(db, "insert_search_run", lambda *args: 20)
    insert, update = MagicMock(), MagicMock()
    monkeypatch.setattr(db, "insert_search_results", insert)
    monkeypatch.setattr(db, "update_search_run", update)
    monkeypatch.setattr(run_search, "get_scraper_config", lambda: {})
    monkeypatch.setattr(run_search, "get_search_fetcher", lambda: "direct")
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    monkeypatch.setattr(run_search.time, "sleep", lambda seconds: None)
    return connection, insert, update


def test_workflow_success(workflow, monkeypatch):
    connection, insert, update = workflow
    monkeypatch.setattr(run_search, "fetch_direct_html", lambda *args, **kwargs: sample())
    summary = run_search.run_search("childhood cancer early diagnosis methods")
    assert summary["status"] == "completed"
    assert summary["final_count"] == 1
    assert len(insert.call_args.args[2]) == 5
    assert connection.commit.call_count == 2
    assert not connection.rollback.called


def test_workflow_failed_fetch(workflow, monkeypatch):
    connection, insert, update = workflow
    def fail(*args, **kwargs):
        raise SearchError("ScraperAPI returned HTTP 401")
    monkeypatch.setattr(run_search, "fetch_direct_html", fail)
    summary = run_search.run_search("childhood cancer early diagnosis methods")
    assert summary["status"] == "failed"
    assert summary["raw_count"] == 0
    assert update.call_args.args[2] == "failed"


def test_storage_failure_rolls_back(workflow, monkeypatch):
    connection, insert, update = workflow
    monkeypatch.setattr(run_search, "fetch_direct_html", lambda *args, **kwargs: sample())
    insert.side_effect = RuntimeError("secret")
    with pytest.raises(SearchError, match="rolled back"):
        run_search.run_search("childhood cancer early diagnosis methods")
    connection.rollback.assert_called_once()
    assert update.call_args.args[2] == "failed"
    assert update.call_args.args[3]["raw_count"] == 0


def test_pagination_preserves_cross_page_duplicates(workflow, monkeypatch):
    monkeypatch.setattr(run_search, "fetch_direct_html", lambda *args, **kwargs: sample())
    summary = run_search.run_search("childhood cancer early diagnosis methods", 2)
    assert summary["raw_count"] == 10
    assert summary["final_count"] == 1
    assert summary["duplicate_count"] == 5


def test_unknown_wrapper_does_not_become_organic():
    rows = parse_results('<div class="MjjYud"><a href="https://example.org"><h3>Unknown</h3></a></div>')
    assert rows[0]["is_ad"] is None
    assert clean_results(rows)[1]["final_count"] == 0


def test_later_page_failure_preserves_first_page(workflow, monkeypatch):
    def fetch(query, start=0):
        if start:
            raise SearchError("ScraperAPI request timed out")
        return sample()
    monkeypatch.setattr(run_search, "fetch_direct_html", fetch)
    summary = run_search.run_search("childhood cancer early diagnosis methods", 2)
    assert summary["status"] == "failed"
    assert summary["raw_count"] == 5
    assert summary["final_count"] == 1


def test_insert_failure_rolls_back_initial_transaction(workflow, monkeypatch):
    def fail(*args):
        raise RuntimeError("secret")
    monkeypatch.setattr(db, "insert_search_run", fail)
    with pytest.raises(SearchError, match="Could not create"):
        run_search.run_search("childhood cancer early diagnosis methods")
    workflow[0].rollback.assert_called_once()
    workflow[0].commit.assert_not_called()


@pytest.mark.parametrize("url", ["relative/path", "https://bad%host.test", "ftp://example.org"])
def test_reject_unsafe_urls(url):
    assert normalize_url(url) is None


def test_pagination_requires_matching_explicit_link():
    from parse_results import next_page_start
    query = "childhood cancer early diagnosis methods"
    assert next_page_start(sample(), query, 0) == 10
    assert next_page_start(sample(), query, 10) is None
    assert next_page_start(sample(), "other query", 0) is None
    assert next_page_start('<a id="pnnext" href="https://evil.example/search?start=10">Next</a>', query, 0) is None


def test_observed_google_enablejs_shell_has_specific_diagnostic():
    html = (FIXTURES / "google_enablejs_shell.html").read_text()
    with pytest.raises(SearchError, match="JavaScript-required redirect shell; no search results"):
        parse_results(html)


def test_enablejs_navigation_does_not_hide_real_observations():
    shell = (FIXTURES / "google_enablejs_shell.html").read_text()
    rows = parse_results(shell + '<div class="g"><a href="https://example.org"><h3>Fixture result</h3></a></div>')
    assert len(rows) == 1
    assert rows[0]["is_ad"] is False
