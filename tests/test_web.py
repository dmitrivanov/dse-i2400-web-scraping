"""Web contracts use mocked ETL/MySQL and local temporary artifact files only."""
from copy import deepcopy
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from mysql.connector import Error
import pytest

import db
import web_search
from main import app

client = TestClient(app)
QUERY = "childhood cancer early diagnosis methods"


def stored_run():
    return {"run": {"id": 12, "query_text": QUERY, "engine": "bing", "status": "completed",
        "raw_count": 1, "ad_count": 0, "duplicate_count": 0, "final_count": 1, "error_message": None},
        "results": [{"id": 4, "run_id": 12, "title": "Fixture title", "original_url": "https://example.org",
            "normalized_url": "https://example.org/", "snippet": "Fixture snippet", "is_ad": None,
            "is_duplicate": False, "result_rank": 1}], "artifacts": []}


@pytest.fixture
def backend(monkeypatch, tmp_path):
    import saved_searches
    monkeypatch.setattr(saved_searches, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(web_search, "ARTIFACT_ROOT", tmp_path)
    run = MagicMock(return_value={"run_id": 12})
    read = MagicMock(side_effect=lambda run_id: deepcopy(stored_run()))
    monkeypatch.setattr(web_search, "run_search", run)
    monkeypatch.setattr(db, "get_search_run", read)
    return run, read


def test_interface_and_static_assets():
    response = client.get('/search')
    assert response.status_code == 200 and 'text/html' in response.headers['content-type']
    assert QUERY in response.text
    assert '>Web</button>' in response.text and '>AI</button>' in response.text
    assert 'aria-label="Google"' in response.text and 'Gemini' in response.text
    assert 'Details &amp; evidence' in response.text
    assert 'CCNY' not in response.text
    assert 'Follow the evidence' not in response.text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200


@pytest.mark.parametrize("body", [
    {"query": "short query"}, {"query": ""}, {"query": "x" * 1001},
    {"query": QUERY, "engine": "unknown"}, {"query": QUERY, "fetcher": "unknown"},
    {"query": QUERY, "engine": "bing", "max_pages": 51},
    {"query": QUERY, "engine": "duckduckgo", "fetcher": 123},
])
def test_search_validation_before_etl(backend, body):
    assert client.post('/api/search', json=body).status_code == 422
    backend[0].assert_not_called()


@pytest.mark.parametrize("engine,fetcher", [(engine, "scraperapi") for engine in ("google", "bing", "yahoo", "duckduckgo")])
def test_search_selection_and_db_readback(backend, engine, fetcher):
    response = client.post('/api/search', json={"query": QUERY, "engine": engine, "fetcher": fetcher})
    assert response.status_code == 200
    backend[0].assert_called_once_with(QUERY, max_pages=1, engine=engine, fetcher=fetcher, capture=False, mode="search", refresh=False, resume_run_id=None, allow_paid=False)
    backend[1].assert_called_once_with(12)
    assert response.json()['run']['fetcher'] == fetcher
    assert response.json()['results'][0]['title'] == 'Fixture title'
    assert response.json()['results'][0]['is_ad'] is None
    assert response.json()['run']['fetcher'] == fetcher


def test_web_defaults_use_structured_google(backend):
    assert client.post('/api/search', json={"query": QUERY}).status_code == 200
    assert backend[0].call_args.kwargs['fetcher'] == 'scraperapi'
    assert backend[0].call_args.kwargs['engine'] == 'google'


def test_provider_failed_run_is_returned_honestly(backend):
    data = stored_run()
    data['results'] = []
    data['run'].update(status='failed', raw_count=0, final_count=0, error_message='Google returned a JavaScript-required redirect shell; no search results')
    backend[1].side_effect = lambda run_id: deepcopy(data)
    response = client.post('/api/search', json={"query": QUERY, "engine": "google"})
    assert response.status_code == 200
    assert response.json()['results'] == []
    assert response.json()['run']['status'] == 'failed'
    assert 'redirect shell' in response.json()['run']['error_message']


def test_empty_successful_run(backend):
    data = stored_run(); data['results'] = []; data['run']['final_count'] = 0
    backend[1].side_effect = lambda run_id: deepcopy(data)
    assert client.get('/api/runs/12').json()['results'] == []


def test_history_and_reopen_do_not_invoke_etl(backend, monkeypatch):
    monkeypatch.setattr(db, 'get_recent_search_runs', lambda: [stored_run()['run']])
    assert client.get('/api/runs').json()[0]['query_text'] == QUERY
    assert client.get('/api/runs/12').json()['run']['fetcher'] is None
    backend[0].assert_not_called()


def test_missing_run(backend):
    backend[1].side_effect = None; backend[1].return_value = None
    assert client.get('/api/runs/12').status_code == 404
    assert client.get('/api/runs/0').status_code == 422


@pytest.mark.parametrize('route,function', [('/api/runs','get_recent_search_runs'),('/api/runs/12','get_search_run')])
def test_db_errors_are_safe(monkeypatch, route, function):
    def fail(*args):
        raise Error('secret-password')
    monkeypatch.setattr(db, function, fail)
    response = client.get(route)
    assert response.status_code == 503
    assert 'secret-password' not in response.text


def test_execution_error_redacted(backend):
    from google_search import SearchError
    backend[0].side_effect = SearchError('secret-key')
    response = client.post('/api/search', json={"query": QUERY})
    assert response.status_code == 502 and 'secret-key' not in response.text


@pytest.mark.parametrize('escape', ['outside', 'traversal', 'symlink', 'missing', 'wrong_extension'])
def test_artifact_access_rejects_unsafe_paths(monkeypatch, tmp_path, escape):
    root = tmp_path / 'artifacts'; root.mkdir()
    outside = tmp_path / 'private.txt'; outside.write_text('secret')
    monkeypatch.setattr(web_search, 'ARTIFACT_ROOT', root)
    if escape == 'outside': path = outside
    elif escape == 'traversal': path = root / '..' / 'private.txt'
    elif escape == 'symlink':
        path = root / 'link.txt'; path.symlink_to(outside)
    elif escape == 'wrong_extension':
        path = root / 'page.html'; path.write_text('secret')
    else: path = root / 'missing.txt'
    monkeypatch.setattr(db, 'get_capture_artifact', lambda artifact_id: {'ocr_text_path':str(path)})
    response = client.get('/api/artifacts/1/ocr')
    assert response.status_code == 404 and 'secret' not in response.text


def test_safe_artifact_and_links(backend, monkeypatch, tmp_path):
    image = tmp_path / 'screen.png'; image.write_bytes(b'fixture PNG')
    text = tmp_path / 'ocr.txt'; text.write_text('Fixture OCR — UTF-8')
    artifact = {'id': 1, 'screenshot_path': str(image), 'ocr_text_path':str(text)}
    monkeypatch.setattr(db, 'get_capture_artifact', lambda artifact_id: artifact)
    data = stored_run(); data['artifacts'] = [artifact]
    backend[1].side_effect = lambda run_id: deepcopy(data)
    response = client.get('/api/runs/12')
    assert str(tmp_path) not in response.text
    assert response.json()['artifacts'][0]['ocr_url'] == '/api/artifacts/1/ocr'
    screenshot = client.get('/api/artifacts/1/screenshot')
    assert screenshot.content == b'fixture PNG'
    assert screenshot.headers['content-type'] == 'image/png'
    ocr = client.get('/api/artifacts/1/ocr')
    assert ocr.text == 'Fixture OCR — UTF-8'
    assert ocr.headers['x-content-type-options'] == 'nosniff'


def test_artifact_missing_and_bad_kind(monkeypatch):
    monkeypatch.setattr(db, 'get_capture_artifact', lambda artifact_id: None)
    assert client.get('/api/artifacts/1/screenshot').status_code == 404
    assert client.get('/api/artifacts/1/html').status_code == 422


def test_read_sql_parameters_and_results():
    connection = MagicMock(); connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = stored_run()['run']
    cursor.fetchall.side_effect = [stored_run()['results'], []]
    from unittest.mock import patch
    with patch.object(db, 'get_connection', return_value=connection):
        data = db.get_search_run(12)
    assert data['results'][0]['title'] == 'Fixture title'
    assert [call.args[1] for call in cursor.execute.call_args_list] == [(12,), (12,), (12,)]


def test_collection_action_error_is_actionable(backend):
    from run_search import CollectionError
    backend[0].side_effect=CollectionError('Increase the total page budget to collect more')
    response=client.post('/api/search',json={'query':QUERY,'mode':'collect','resume_run_id':12})
    assert response.status_code==400
    assert response.json()['detail']=='Increase the total page budget to collect more'


def test_options_report_bounded_config_without_search(backend,monkeypatch):
    monkeypatch.setattr(web_search,'get_collection_page_limit',lambda:12)
    assert client.get('/api/search-options').json()=={'collection_max_pages':12,'max_allowed_pages':50}
    backend[0].assert_not_called()


def test_web_rejects_legacy_production_choices(backend):
    for body in [{'query':QUERY,'engine':'unsupported'}, {'query':QUERY,'engine':'bing','fetcher':'direct'},
                 {'query':QUERY,'fetcher':'direct'}]:
        assert client.post('/api/search',json=body).status_code==422
    backend[0].assert_not_called()
