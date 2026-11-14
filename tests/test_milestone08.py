"""Library, classification, display metadata and offline Gemini contracts."""
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
import config
import db
import library
from main import app
from google_search import parse_organic_results, SearchError
from gemini_provider import validate_configuration

client = TestClient(app)


def test_library_pagination_is_parameterized(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{'id': 1}, {'id': 2}, {'id': 3}]
    monkeypatch.setattr(db, 'get_connection', MagicMock(return_value=connection))
    result = library.read_library('ai', 2, 2)
    assert result == {'items': [{'id': 1}, {'id': 2}], 'page': 2, 'has_more': True}
    sql, values = cursor.execute.call_args.args
    assert values == ('ai', 3, 2)
    assert 'WHERE search_type=%s' in sql
    assert 'WHERE a.run_id IS NULL' in sql
    assert 'CASE WHEN r.engine IN' in sql
    assert "THEN 'web' END) AS search_type" in sql  # unmatched historical engines remain NULL


@pytest.mark.parametrize('query', ['page=0', 'page_size=101', 'search_type=invalid'])
def test_library_rejects_invalid_parameters(query):
    assert client.get('/api/library?' + query).status_code == 422


def test_library_route_is_read_only(monkeypatch):
    read = MagicMock(return_value={'items': [], 'page': 1, 'has_more': False})
    monkeypatch.setattr(library, 'read_library', read)
    assert client.get('/api/library?search_type=web').json()['items'] == []
    read.assert_called_once_with('web', 1, 20)


def test_saved_ai_preserves_actual_model_and_text(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {'id': 2, 'model_name': 'actual-saved-model', 'response_text': '<script>saved text</script>'}
    monkeypatch.setattr(db, 'get_connection', MagicMock(return_value=connection))
    data = client.get('/api/library/response/2').json()
    assert data['responses'][0]['model_name'] == 'actual-saved-model'
    assert data['summaries'] == []
    assert cursor.execute.call_args.args[1] == (2,)


def test_missing_saved_ai(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    monkeypatch.setattr(db, 'get_connection', MagicMock(return_value=connection))
    assert client.get('/api/library/summary/42').status_code == 404


def test_gemini_offline_configuration_never_returns_secret(monkeypatch):
    monkeypatch.setattr(config, 'load_dotenv', lambda *args: None)
    monkeypatch.setenv('GEMINI_API_KEY', 'secret-not-for-browser')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    result = validate_configuration()
    assert result == {'provider': 'gemini', 'model': 'gemini-3.5-flash-lite', 'configured': True, 'execution_available': True}
    assert 'secret-not-for-browser' not in str(result)
    assert 'GEMINI_API_KEY' not in client.get('/search').text


@pytest.mark.parametrize('key,model', [('', 'gemini-3.5-flash-lite'), ('private', ''), ('private', 'https://bad/key'), ('private', 'not-gemini')])
def test_invalid_gemini_configuration_is_safe(monkeypatch, key, model):
    monkeypatch.setattr(config, 'load_dotenv', lambda *args: None)
    monkeypatch.setenv('GEMINI_API_KEY', key)
    monkeypatch.setenv('GEMINI_MODEL', model)
    with pytest.raises(ValueError) as error:
        validate_configuration()
    assert 'private' not in str(error.value)


def test_displayed_link_is_preserved_without_changing_destination():
    result = parse_organic_results({'organic_results': [{'link': 'https://www.google.com/goto?token=opaque', 'displayed_link': 'https://publisher.example › Research', 'position': 3}]})[0]
    assert result['original_url'] == 'https://www.google.com/goto?token=opaque'
    assert result['displayed_link'] == 'https://publisher.example › Research'
    assert result['result_rank'] == 3
    with pytest.raises(SearchError):
        parse_organic_results({'organic_results': [{'link': 'https://example.org', 'displayed_link': {}}]})


def test_observation_metadata_persisted(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    row = {'title': 'Title', 'original_url': 'https://example.org', 'normalized_url': 'https://example.org', 'snippet': 'Snippet', 'result_rank': 2, 'is_ad': False, 'is_duplicate': False, 'page_number': 1, 'displayed_link': 'example.org'}
    db.insert_search_results(connection, 9, [row])
    values = connection.cursor.return_value.__enter__.return_value.execute.call_args.args[1]
    assert values[-2:] == (1, 'example.org')
