"""Engine fixtures and mocked retrieval/database checks; no real network or writes."""
import base64
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

import bing_search
import duckduckgo_search
import db
import run_search
from clean_urls import clean_results, normalize_url
from google_search import SearchError

FIXTURES = Path(__file__).parent / "fixtures"
QUERY = "childhood cancer early diagnosis methods"


def test_bing_observed_cards():
    html = (FIXTURES / "bing_results.html").read_text()
    rows = bing_search.parse_results(html)
    assert len(rows) == 2
    assert rows[0]["title"] == "CHILDHOOD Definition & Meaning - Merriam-Webster"
    assert rows[0]["snippet"]
    assert rows[0]["is_ad"] is False
    cleaned, counts = clean_results(rows)
    assert counts["final_count"] == 2
    assert cleaned[0]["normalized_url"] == "https://www.merriam-webster.com/dictionary/childhood"
    assert bing_search.next_page_start(html, QUERY, 0) == 11
    assert bing_search.next_page_start(html, QUERY, 11) is None
    assert bing_search.next_page_start(html, "other query", 0) is None


def test_bing_navigation_missing_fields_and_ads():
    html = '''<a href="https://navigation.example">Navigation</a><ol id="b_results">
    <li class="b_algo"><h2>No link</h2></li>
    <li class="b_ad"><h2><a href="https://ad.example">Ad</a></h2></li></ol>'''
    rows = bing_search.parse_results(html)
    assert len(rows) == 1 and rows[0]["is_ad"] is True
    assert rows[0]["snippet"] is None


def test_ddg_fixture():
    html = (FIXTURES / "duckduckgo_results.html").read_text()
    rows = duckduckgo_search.parse_results(html)
    assert [row["is_ad"] for row in rows] == [False, True, None]
    assert rows[0]["snippet"] == "Fixture snippet"
    cleaned, counts = clean_results(rows)
    assert cleaned[0]["normalized_url"] == "https://example.org/diagnosis"
    assert counts == {"raw_count": 3, "ad_count": 1, "duplicate_count": 0, "final_count": 1}
    token = duckduckgo_search.next_page_start(html, QUERY, 0)
    assert token == {"method": "post", "params": {"q": QUERY, "s": "30", "vqd": "fixture-token"}}
    assert duckduckgo_search.next_page_start(html, QUERY, token) is None
    assert duckduckgo_search.next_page_start(html, "other query", 0) is None
    assert duckduckgo_search.next_page_start(html.replace('action="/html/"', 'action="https://evil.example/html/"'), QUERY, 0) is None


@pytest.mark.parametrize("engine, html", [
    (bing_search, "<div id='b_captcha'></div>"),
    (duckduckgo_search, '<form id="challenge-form"></form>'),
    (bing_search, '<a href="https://example.org">Navigation</a>'),
    (duckduckgo_search, '<a href="https://example.org">Navigation</a>'),
])
def test_unsupported_and_blocked_html(engine, html):
    with pytest.raises(SearchError):
        engine.parse_results(html)


@pytest.mark.parametrize("engine", [bing_search, duckduckgo_search])
@pytest.mark.parametrize("status, body", [(302, "redirect"), (403, "denied"), (202, "challenge"), (200, " ")])
def test_http_failures(monkeypatch, engine, status, body):
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(status, text=body))
    with pytest.raises(SearchError):
        engine.fetch_html(QUERY)


@pytest.mark.parametrize("engine", [bing_search, duckduckgo_search])
@pytest.mark.parametrize("error", [httpx.ConnectError("secret"), httpx.ReadTimeout("secret")])
def test_safe_network_failure(monkeypatch, engine, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(SearchError) as failure:
        engine.fetch_html(QUERY)
    assert "secret" not in str(failure.value)


def test_ddg_observed_next_form_submission(monkeypatch):
    token = duckduckgo_search.next_page_start((FIXTURES / "duckduckgo_results.html").read_text(), QUERY, 0)
    def post(url, **kwargs):
        assert url == duckduckgo_search.ENDPOINT
        assert kwargs["data"]["q"] == QUERY
        assert kwargs["data"]["vqd"] == "fixture-token"
        assert kwargs["data"]["s"] == "30"
        return httpx.Response(200, text="<html>fixture</html>")
    monkeypatch.setattr(httpx, "post", post)
    assert duckduckgo_search.fetch_html(QUERY, token) == "<html>fixture</html>"


@pytest.mark.parametrize("url, expected", [
    ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa", "https://example.org/a"),
    ("/l/?uddg=https%3A%2F%2Fexample.org%2Fa", "https://example.org/a"),
    ("https://duckduckgo.com/l/?uddg=javascript%3Aalert(1)", None),
    ("https://www.bing.com/ck/a?u=a1!!!!", None),
    ("https://www.bing.com/ck/a?u=javascript%3Aalert(1)", None),
    ("https://www.bing.com/ck/a", None),
    ("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa%20b", None),
])
def test_redirect_normalization(url, expected):
    assert normalize_url(url) == expected


def test_cross_engine_duplicates_have_common_normalization():
    target = "https://example.org/a"
    encoded = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    rows = [{"original_url": url, "is_ad": False} for url in [
        target, "https://www.bing.com/ck/a?u=a1" + encoded,
        "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa"]]
    _, counts = clean_results(rows)
    assert counts["final_count"] == 1 and counts["duplicate_count"] == 2


@pytest.mark.parametrize("engine,module,fixture", [
    ("bing", bing_search, "bing_results.html"),
    ("duckduckgo", duckduckgo_search, "duckduckgo_results.html"),
])
def test_shared_etl_engine_and_persistence(monkeypatch, tmp_path, engine, module, fixture):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db, "insert_search_query", lambda *args: 10)
    create_run, save_results, update = MagicMock(return_value=20), MagicMock(), MagicMock()
    monkeypatch.setattr(db, "insert_search_run", create_run)
    monkeypatch.setattr(db, "insert_search_results", save_results)
    monkeypatch.setattr(db, "update_search_run", update)
    monkeypatch.setattr(run_search, "get_search_fetcher", lambda: pytest.fail("Google configuration used by other engine"))
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    monkeypatch.setattr(module, "fetch_html", lambda *args, **kwargs: (FIXTURES / fixture).read_text())
    summary = run_search.run_search(QUERY, engine=engine)
    create_run.assert_called_once_with(connection, 10, engine)
    assert summary["engine"] == engine and summary["status"] == "completed"
    assert save_results.call_args.args[1] == 20
    assert update.call_args.args[2] == "completed"
    assert connection.commit.call_count == 2


def test_db_engine_is_parameterized():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.lastrowid = 12
    assert db.insert_search_run(connection, 10, "duckduckgo") == 12
    assert cursor.execute.call_args.args[1] == (10, "duckduckgo", "running")
    assert "%s" in cursor.execute.call_args.args[0]


@pytest.mark.parametrize("engine,fetcher", [("unknown", None), ("bing", "invalid"), ("duckduckgo", "invalid")])
def test_unsupported_engine_fetcher_fails_before_writes(engine, fetcher):
    with pytest.raises(ValueError):
        run_search.run_search(QUERY, engine=engine, fetcher=fetcher)


@pytest.mark.parametrize("module", [bing_search, duckduckgo_search])
def test_encoded_query_and_no_redirect_following(monkeypatch, module):
    query = "childhood cancer diagnosis & early methods"
    def respond(url, **kwargs):
        request = httpx.Request("GET", url, params=kwargs["params"])
        assert request.url.params["q"] == query
        assert "%26" in str(request.url)
        assert kwargs["follow_redirects"] is False
        return httpx.Response(200, text="fixture")
    monkeypatch.setattr(httpx, "get", respond)
    assert module.fetch_html(query) == "fixture"


@pytest.mark.parametrize("engine,module", [("bing", bing_search), ("duckduckgo", duckduckgo_search)])
def test_engine_failure_is_persisted_safely(monkeypatch, tmp_path, engine, module):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db, "insert_search_query", lambda *args: 10)
    monkeypatch.setattr(db, "insert_search_run", lambda *args: 20)
    save, update = MagicMock(), MagicMock()
    monkeypatch.setattr(db, "insert_search_results", save)
    monkeypatch.setattr(db, "update_search_run", update)
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    def fail(*args, **kwargs):
        raise SearchError("Observed engine block")
    monkeypatch.setattr(module, "fetch_html", fail)
    summary = run_search.run_search(QUERY, engine=engine)
    assert summary["status"] == "failed" and summary["raw_count"] == 0
    assert update.call_args.args[2] == "failed"
    assert update.call_args.args[4] == "Observed engine block"
    assert connection.commit.call_count == 2


def test_bing_shared_pipeline_pagination_and_dedup(monkeypatch, tmp_path):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db, "get_connection", lambda: connection)
    monkeypatch.setattr(db, "insert_search_query", lambda *args: 10)
    monkeypatch.setattr(db, "insert_search_run", lambda *args: 20)
    save = MagicMock()
    monkeypatch.setattr(db, "insert_search_results", save)
    monkeypatch.setattr(db, "update_search_run", MagicMock())
    monkeypatch.setattr(run_search, "__file__", str(tmp_path / "run_search.py"))
    monkeypatch.setattr(run_search.time, "sleep", lambda seconds: None)
    fetch = MagicMock(return_value=(FIXTURES / "bing_results.html").read_text())
    monkeypatch.setattr(bing_search, "fetch_html", fetch)
    summary = run_search.run_search(QUERY, max_pages=5, engine="bing")
    assert summary["pages"] == 2
    assert summary["raw_count"] == 4 and summary["duplicate_count"] == 2
    assert summary["final_count"] == 2
    assert fetch.call_count == 2
    assert fetch.call_args_list[1].kwargs["start"] == 11
    assert len(save.call_args.args[2]) == 4


@pytest.mark.parametrize('module,expected_host', [(bing_search,'www.bing.com'), (duckduckgo_search,'html.duckduckgo.com')])
def test_explicit_paid_fetcher_preserves_arbitrary_query(monkeypatch, module, expected_host):
    from urllib.parse import urlsplit, parse_qs
    import config
    query = 'Childhood cancer morbidity rate “ethnicity or race”'
    monkeypatch.setattr(config,'get_scraper_config',lambda: {'api_key':'fixture-secret','base_url':'https://api.scraperapi.com'})
    def response(url, **kwargs):
        assert url=='https://api.scraperapi.com'
        target=urlsplit(kwargs['params']['url'])
        assert target.hostname==expected_host
        assert parse_qs(target.query)['q']==[query]
        assert kwargs['params']['api_key']=='fixture-secret'
        return httpx.Response(200,text='<html>fixture-secret</html>')
    monkeypatch.setattr(httpx,'get',response)
    assert 'fixture-secret' not in module.fetch_scraper_html(query)


def test_paid_ddg_does_not_silently_convert_post_pagination():
    with pytest.raises(SearchError,match='POST pagination is not supported'):
        duckduckgo_search.fetch_scraper_html(QUERY, {'method':'post','params':{'q':QUERY,'s':'30'}})


@pytest.mark.parametrize('engine,module', [('bing',bing_search),('duckduckgo',duckduckgo_search)])
def test_paid_selection_is_not_an_automatic_fallback(monkeypatch,tmp_path,engine,module):
    import config
    connection=MagicMock(); connection.__enter__.return_value=connection
    monkeypatch.setattr(db,'get_connection',lambda:connection)
    monkeypatch.setattr(db,'insert_search_query',lambda *args:10)
    monkeypatch.setattr(db,'insert_search_run',lambda *args:20)
    monkeypatch.setattr(db,'insert_search_results',MagicMock())
    monkeypatch.setattr(db,'update_search_run',MagicMock())
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:{})
    monkeypatch.setattr(run_search,'__file__',str(tmp_path/'run_search.py'))
    direct=MagicMock(side_effect=SearchError('Direct blocked'))
    paid=MagicMock(side_effect=SearchError('ScraperAPI returned HTTP 401'))
    monkeypatch.setattr(module,'fetch_html',direct)
    monkeypatch.setattr(module,'fetch_scraper_html',paid)
    summary=run_search.run_search(QUERY,engine=engine)
    assert summary['status']=='failed'
    paid.assert_not_called()
    summary=run_search.run_search(QUERY,engine=engine,fetcher='scraperapi')
    assert summary['fetcher']=='scraperapi' and summary['status']=='failed'
    assert paid.call_count==1 and direct.call_count==1
