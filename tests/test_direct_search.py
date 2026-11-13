"""Direct retrieval and fetcher selection; all HTTP and database calls are mocked."""
from unittest.mock import MagicMock

import httpx
import pytest

import config
import google_search
import run_search
from google_search import SearchError
from parse_results import parse_results


@pytest.mark.parametrize("status, body, diagnostic", [
    (403, "denied", "HTTP 403"), (429, "limited", "HTTP 429"),
    (302, "", "HTTP 302"), (200, " ", "empty response"),
    (200, '<form action="https://consent.google.com/save"></form>', "consent"),
    (200, '<div class="g-recaptcha"></div>', "CAPTCHA"),
    (200, '<title>Access denied</title>', "access-denied"),
])
def test_direct_errors(monkeypatch, status, body, diagnostic):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(status, text=body))
    with pytest.raises(SearchError, match=diagnostic):
        google_search.fetch_direct_html("arbitrary valid search query about science")


@pytest.mark.parametrize("error, diagnostic", [
    (httpx.ReadTimeout("sensitive-url"), "timed out"),
    (httpx.ConnectError("sensitive-url"), "network request failed"),
])
def test_direct_network_errors(monkeypatch, error, diagnostic):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(SearchError, match=diagnostic) as failure:
        google_search.fetch_direct_html("query")
    assert "sensitive" not in str(failure.value)


def test_direct_encoding_and_parser_compatibility(monkeypatch):
    query = "early diagnosis methods cancer & childhood"
    body = '<div class="g"><a href="https://example.org"><h3>Fixture result</h3></a></div>'
    def respond(url, **kwargs):
        request = httpx.Request("GET", url, params=kwargs["params"])
        assert request.url.params["q"] == query
        assert "%26" in str(request.url)
        assert kwargs["follow_redirects"] is False
        assert "MY_CUSTOM_BOT" in kwargs["headers"]["User-Agent"]
        assert "api_key" not in kwargs["params"]
        return httpx.Response(200, text=body)
    monkeypatch.setattr(httpx, "get", respond)
    rows = parse_results(google_search.fetch_direct_html(query))
    assert rows[0]["is_ad"] is False


def test_http_200_redirect_shell_is_not_results(monkeypatch):
    body = '<title>Google Search</title><p>Please click here if you are not redirected within a few seconds.</p>'
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(200, text=body))
    with pytest.raises(SearchError, match="No supported linked result headings"):
        parse_results(google_search.fetch_direct_html("query"))


@pytest.mark.parametrize("environment, expected", [(None, "scraperapi"), ("direct", "direct"), ("scraperapi", "scraperapi")])
def test_fetcher_configuration(monkeypatch, environment, expected):
    monkeypatch.setattr(config, "load_dotenv", lambda *args: None)
    if environment is None:
        monkeypatch.delenv("SEARCH_FETCHER", raising=False)
    else:
        monkeypatch.setenv("SEARCH_FETCHER", environment)
    monkeypatch.delenv("SCRAPER_API_KEY", raising=False)
    assert config.get_search_fetcher() == expected


@pytest.mark.parametrize("explicit, configured, expected", [
    (None, "direct", "direct"), (None, "scraperapi", "scraperapi"),
    ("direct", "scraperapi", "direct"), ("scraperapi", "direct", "scraperapi"),
])
def test_workflow_selection(monkeypatch, tmp_path, explicit, configured, expected):
    import db
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db, "insert_search_query", lambda *args: 1)
    monkeypatch.setattr(db, "insert_search_run", lambda *args: 2)
    monkeypatch.setattr(db, "insert_search_results", MagicMock())
    monkeypatch.setattr(db, "update_search_run", MagicMock())
    monkeypatch.setattr(run_search, "get_search_fetcher", lambda: configured)
    scraper_config = MagicMock()
    monkeypatch.setattr(run_search, "get_scraper_config", scraper_config)
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    body = '<div class="g"><a href="https://example.org"><h3>Fixture</h3></a></div>'
    direct = MagicMock(return_value=body)
    paid = MagicMock(return_value={"organic_results": [{"title": "Fixture result", "link": "https://example.org", "position": 1}]})
    monkeypatch.setattr(run_search, "fetch_direct_html", direct)
    monkeypatch.setattr(run_search, "fetch_results", paid)
    summary = run_search.run_search("childhood cancer early diagnosis methods", fetcher=explicit)
    assert summary["fetcher"] == expected
    assert summary["final_count"] == 1
    assert direct.call_count == (expected == "direct")
    assert paid.call_count == (expected == "scraperapi")
    assert scraper_config.call_count == (expected == "scraperapi")
