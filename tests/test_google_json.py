"""Structured Google JSON tests: no network, credentials, or real database writes."""
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

import db
import google_search
import run_search
from clean_urls import clean_results
from google_search import SearchError
from main import app

QUERY = '  Childhood cancer early diagnosis methods “referral”  '
URL = 'https://www.google.com/url?q=https%3A%2F%2Fexample.org&sa=U&utm_source=google#fragment'


def payload(count=1):
    return {'organic_results': [{'title': 'Fixture title', 'link': URL, 'snippet': 'Fixture snippet', 'position': 7} for _ in range(count)],
            'ads': [{'title': 'Ignored fixture ad'}], 'pagination': {'next_page_url': 'https://api.scraperapi.com/?api_key=do-not-follow'}}


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setattr(google_search, 'get_scraper_config', lambda: {'base_url': 'https://api.scraperapi.com', 'api_key': 'test-secret'})


def test_requests_endpoint_exact_query_and_start(settings, monkeypatch):
    response = MagicMock(status_code=200)
    response.json.return_value = payload()
    def get(url, **kwargs):
        assert url == 'https://api.scraperapi.com/structured/google/search/v1'
        assert kwargs['params'] == {'api_key': 'test-secret', 'query': QUERY, 'start': 20}
        assert kwargs['allow_redirects'] is False
        assert kwargs['timeout'] == (10, 60)
        return response
    monkeypatch.setattr(requests, 'get', get)
    assert google_search.fetch_results(QUERY, 20) == payload()


def test_mapping_preserves_positions_links_and_only_organic():
    rows = google_search.parse_organic_results(payload(2))
    assert len(rows) == 2 and rows[0]['result_rank'] == 7
    assert rows[0]['title'] == 'Fixture title' and rows[0]['snippet'] == 'Fixture snippet'
    assert rows[0]['original_url'] == URL and rows[0]['is_ad'] is False
    cleaned, counts = clean_results(rows, preserve_urls=True)
    assert cleaned[0]['normalized_url'] == URL
    assert counts == {'raw_count': 2, 'ad_count': 0, 'duplicate_count': 1, 'final_count': 1}


def test_missing_optional_fields_are_not_invented():
    row = google_search.parse_organic_results({'organic_results': [{'link': 'https://example.org'}]})[0]
    assert row['title'] is None and row['snippet'] is None and row['result_rank'] is None


@pytest.mark.parametrize('data', [{'organic_results': [{'title': 'Missing URL'}]}, {'organic_results': [{'link': URL, 'position': 'one'}]}, {'organic_results': [{'link': URL, 'title': []}]}])
def test_malformed_result_rejected(data):
    with pytest.raises(SearchError):
        google_search.parse_organic_results(data)


@pytest.mark.parametrize('status,data', [(401, {}), (429, {}), (500, {}), (200, {}), (200, []), (200, {'organic_results': None})])
def test_safe_response_errors(settings, monkeypatch, status, data):
    response = MagicMock(status_code=status)
    response.json.return_value = data
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: response)
    with pytest.raises(SearchError) as error:
        google_search.fetch_results(QUERY)
    assert 'test-secret' not in str(error.value)


def test_invalid_json(settings, monkeypatch):
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError('test-secret')
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: response)
    with pytest.raises(SearchError, match='invalid JSON'):
        google_search.fetch_results(QUERY)


@pytest.mark.parametrize('failure', [requests.Timeout('test-secret'), requests.ConnectionError('test-secret')])
def test_safe_requests_errors(settings, monkeypatch, failure):
    def fail(*args, **kwargs): raise failure
    monkeypatch.setattr(requests, 'get', fail)
    with pytest.raises(SearchError) as error:
        google_search.fetch_results(QUERY)
    assert 'test-secret' not in str(error.value)


@pytest.fixture
def workflow(monkeypatch, tmp_path):
    connection = MagicMock(); connection.__enter__.return_value = connection
    monkeypatch.setattr(db, 'get_connection', lambda: connection)
    query = MagicMock(return_value=1)
    monkeypatch.setattr(db, 'insert_search_query', query)
    monkeypatch.setattr(db, 'insert_search_run', lambda *args: 2)
    save, update = MagicMock(), MagicMock()
    monkeypatch.setattr(db, 'insert_search_results', save)
    monkeypatch.setattr(db, 'update_search_run', update)
    monkeypatch.setattr(run_search, 'get_scraper_config', lambda: {})
    monkeypatch.setattr(run_search, '__file__', str(tmp_path / 'run_search.py'))
    monkeypatch.setattr(run_search.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(run_search, 'find_saved_collection', lambda *args: None)
    return query, save, update


def test_exact_query_pagination_and_duplicate_stop(workflow, monkeypatch):
    fetch = MagicMock(return_value=payload())
    monkeypatch.setattr(google_search, 'fetch_results', fetch)
    summary = run_search.run_search(QUERY, max_pages=5, engine='google', fetcher='scraperapi', mode='collect')
    assert summary['pages'] == 2 and summary['final_count'] == 1
    assert summary['duplicate_count'] == 1 and summary['raw_count'] == 2
    workflow[0].assert_called_once()
    assert workflow[0].call_args.args[1] == QUERY
    assert [call.kwargs['start'] for call in fetch.call_args_list] == [0, 10]
    assert all(call.args[0] == QUERY for call in fetch.call_args_list)
    assert [row['result_rank'] for row in workflow[1].call_args.args[2]] == [7, 7]
    assert all(row['normalized_url'] == URL for row in workflow[1].call_args.args[2])


def test_explicit_page_limit(workflow, monkeypatch):
    fetch = MagicMock(return_value=payload())
    monkeypatch.setattr(google_search, 'fetch_results', fetch)
    assert run_search.run_search(QUERY, max_pages=1, fetcher='scraperapi')['pages'] == 1
    fetch.assert_called_once_with(QUERY, start=0)


def test_empty_organic_results_do_not_spend_another_page(workflow, monkeypatch):
    fetch = MagicMock(return_value={'organic_results': []})
    monkeypatch.setattr(google_search, 'fetch_results', fetch)
    summary = run_search.run_search(QUERY, max_pages=5, fetcher='scraperapi', mode='collect')
    assert summary['status'] == 'completed' and summary['raw_count'] == 0
    fetch.assert_called_once()


def test_target_50_unique_and_offsets(workflow, monkeypatch):
    def fetch(query, start=0):
        return {'organic_results': [{'title': 'Fixture', 'link': f'https://example.org/{n}', 'position': n+1} for n in range(start,start+10)]}
    mocked = MagicMock(side_effect=fetch)
    monkeypatch.setattr(google_search, 'fetch_results', mocked)
    summary = run_search.run_search(QUERY, max_pages=5, fetcher='scraperapi', mode='collect')
    assert summary['final_count'] == 50 and summary['pages'] == 5
    assert [call.kwargs['start'] for call in mocked.call_args_list] == [0,10,20,30,40]


def test_next_page_failure_preserves_first_page(workflow, monkeypatch):
    def fetch(query, start=0):
        if start: raise SearchError('Structured Google returned HTTP 429')
        return payload()
    monkeypatch.setattr(google_search, 'fetch_results', fetch)
    summary = run_search.run_search(QUERY, max_pages=5, fetcher='scraperapi', mode='collect')
    assert summary['status'] == 'failed' and summary['raw_count'] == 1 and summary['final_count'] == 1
    assert workflow[2].call_args.args[2] == 'failed'


@pytest.mark.parametrize('pages', [0, 6, True, '5'])
def test_web_page_limits(pages):
    assert TestClient(app).post('/api/search', json={'query': QUERY, 'max_pages': pages}).status_code == 422


def test_provider_declared_last_page_does_not_fetch_again(workflow, monkeypatch):
    data = payload(); data['pagination'] = {'next_page_url': None}
    fetch = MagicMock(return_value=data)
    monkeypatch.setattr(google_search, 'fetch_results', fetch)
    summary = run_search.run_search(QUERY, max_pages=5, fetcher='scraperapi', mode='collect')
    assert summary['pages'] == 1
    fetch.assert_called_once()


def test_web_forwards_page_limit_and_exact_query(monkeypatch, tmp_path):
    import web_search
    from copy import deepcopy
    monkeypatch.setattr(web_search, 'ARTIFACT_ROOT', tmp_path)
    fetch = MagicMock(return_value={'run_id': 23, 'pages': 2})
    monkeypatch.setattr(web_search, 'run_search', fetch)
    data = {'run': {'id':23, 'query_text': QUERY, 'engine':'google', 'final_count':0}, 'results':[], 'artifacts':[]}
    monkeypatch.setattr(db, 'get_search_run', lambda run_id:deepcopy(data))
    response = TestClient(app).post('/api/search', json={'query':QUERY, 'engine':'google', 'max_pages':2, 'mode':'collect'})
    assert response.status_code == 200
    fetch.assert_called_once_with(QUERY, max_pages=2, engine='google', fetcher='scraperapi', capture=False, mode='collect', refresh=False, resume_run_id=None)
    assert response.json()['run']['query_text'] == QUERY
