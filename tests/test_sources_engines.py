"""Real-structure sanitized fixtures and mocked retrieval; no paid requests."""
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs,urlsplit
import pytest
import engine_search
from google_search import SearchError
from search_providers import get_provider
from source_library import rank_sources,read_sources
from source_identity import source_id
from clean_urls import normalize_url
from main import app
from fastapi.testclient import TestClient

QUERY='childhood cancer early diagnosis methods'


@pytest.mark.parametrize('engine,count,next_start',[('bing',10,11),('yahoo',7,8),('duckduckgo',10,10)])
def test_observed_provider_structures(engine,count,next_start):
    html=Path(f'tests/fixtures/scraperapi_{engine}.html').read_text()
    rows,offset=engine_search.parse_page(engine,html,QUERY)
    assert len(rows)==count and offset==next_start
    assert all(row['title'] and row['original_url'].startswith('https://') and not row['is_ad'] for row in rows)
    assert engine_search.parse_page(engine,html,'different original query')[1] is None


@pytest.mark.parametrize('engine',['bing','yahoo','duckduckgo'])
def test_selected_provider_uses_scraper_url_transport(monkeypatch,engine):
    get=MagicMock(return_value=MagicMock(status_code=200,text='fixture'))
    monkeypatch.setattr(engine_search.requests,'get',get)
    monkeypatch.setattr(engine_search,'get_scraper_config',lambda:{'base_url':'https://api.scraperapi.com','api_key':'private'})
    exact='  Childhood cancer early diagnosis methods  '
    assert engine_search.fetch_html(engine,exact)=='fixture'
    params=get.call_args.kwargs['params'];query=parse_qs(urlsplit(params['url']).query)
    assert query['p' if engine=='yahoo' else 'q']==[exact]
    assert get.call_args.args[0]=='https://api.scraperapi.com/'
    assert get_provider(engine,'scraperapi')[0]==f'{engine}:scraperapi:html'


def test_no_fallback_on_provider_error(monkeypatch):
    get=MagicMock(return_value=MagicMock(status_code=403))
    monkeypatch.setattr(engine_search.requests,'get',get)
    monkeypatch.setattr(engine_search,'get_scraper_config',lambda:{'base_url':'https://api.scraperapi.com','api_key':'DO-NOT-PRINT'})
    with pytest.raises(SearchError) as error:engine_search.fetch_html('yahoo',QUERY)
    assert 'DO-NOT-PRINT' not in str(error.value)
    get.assert_called_once()


def test_challenges_and_shells_are_not_results():
    with pytest.raises(SearchError):engine_search.parse_page('duckduckgo','<div class="anomaly-modal">verify</div>',QUERY)
    with pytest.raises(SearchError):engine_search.parse_page('yahoo','<a href="https://example.org">Navigation</a>',QUERY)


def test_yahoo_static_destination_identity_without_network():
    assert normalize_url('https://r.search.yahoo.com/RU=https%3A%2F%2Fexample.org%2Fpaper/RK=2/RS=opaque')=='https://example.org/paper'


def test_cosine_search_ranks_titles_snippets_and_ignores_fillers():
    rows=[{'id':1,'title':'Early childhood cancer diagnosis','snippet':'Methods for referral'},
          {'id':2,'title':'Dictionary: childhood','snippet':'Definitions and examples'},
          {'id':3,'title':'Pediatric oncology referral','snippet':'Early cancer diagnosis methods'}]
    ranked=rank_sources(rows,'please show me cancer diagnosis methods')
    assert {row['id'] for row in ranked}=={1,3}
    assert all(0<row['similarity']<=1 for row in ranked)
    assert rank_sources(rows,'unmatchedword')==[]


def test_identity_upsert_reuses_a_source_without_deleting_observations():
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value;cursor.lastrowid=8
    assert source_id(connection,'https://example.org/paper')==8
    sql,args=cursor.execute.call_args.args
    assert 'ON DUPLICATE KEY UPDATE' in sql and args[1]=='https://example.org/paper'
    assert len(args[0])==32 and 'DELETE' not in sql


def test_full_library_pagination_and_count(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[{'id':i,'title':'Cancer diagnosis','snippet':'Research','created_at':'2026-11-13'} for i in range(181)]
    monkeypatch.setattr('db.get_connection',lambda:connection)
    result=read_sources('',2,25,'web')
    assert result['total']==181 and result['stored_count']==181 and len(result['items'])==25
    assert result['has_more']


def test_source_library_validation():
    client=TestClient(app)
    for query in ['page=0','page_size=101','q='+'x'*1001]:
        assert client.get('/api/library/sources?'+query).status_code==422


def test_ai_source_summaries_only_use_grounded_associations(monkeypatch):
    import ai_routes
    data={'response':{'grounding_metadata':{'grounding_supports':[{'segment':{'text':'Actual source-associated claim'},'grounding_chunk_indices':[0]}]}},
          'sources':[{'chunk_index':0},{'chunk_index':1}],'summary':None}
    monkeypatch.setattr(ai_routes.ai_store,'read_response',lambda response_id:data)
    result=ai_routes.read_packet(1)
    assert result['sources'][0]['summary']=='Actual source-associated claim'
    assert result['sources'][1]['summary'] is None
