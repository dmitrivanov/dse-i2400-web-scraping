"""Retained Bing CLI/provider regression tests; obsolete DuckDuckGo tests removed."""
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

import bing_search
import db
from clean_urls import clean_results
from google_search import SearchError
from search_providers import get_provider

FIXTURES = Path(__file__).parent / 'fixtures'
QUERY = 'childhood cancer early diagnosis methods'


def test_bing_observed_cards():
    html=(FIXTURES/'bing_results.html').read_text()
    rows=bing_search.parse_results(html)
    assert len(rows)==2 and rows[0]['title']=='CHILDHOOD Definition & Meaning - Merriam-Webster'
    assert clean_results(rows)[1]['final_count']==2
    assert bing_search.next_page_start(html,QUERY,0)==11
    assert bing_search.next_page_start(html,QUERY,11) is None
    assert bing_search.next_page_start(html,'other query',0) is None


def test_bing_navigation_missing_fields_and_ads():
    html='<a href="https://navigation.example">Navigation</a><ol id="b_results"><li class="b_algo"><h2>No link</h2></li><li class="b_ad"><h2><a href="https://ad.example">Ad</a></h2></li></ol>'
    rows=bing_search.parse_results(html)
    assert len(rows)==1 and rows[0]['is_ad'] is True and rows[0]['snippet'] is None


@pytest.mark.parametrize('html',['<div id="b_captcha"></div>','<a href="https://example.org">Navigation</a>'])
def test_unsupported_and_blocked_html(html):
    with pytest.raises(SearchError):bing_search.parse_results(html)


@pytest.mark.parametrize('status,body',[(302,'redirect'),(403,'blocked'),(200,' ')])
def test_http_failures(monkeypatch,status,body):
    monkeypatch.setattr(httpx,'get',lambda *args,**kwargs:httpx.Response(status,text=body))
    with pytest.raises(SearchError):bing_search.fetch_html(QUERY)


@pytest.mark.parametrize('failure',[httpx.ConnectError('secret'),httpx.ReadTimeout('secret')])
def test_network_failure(monkeypatch,failure):
    def fail(*args,**kwargs):raise failure
    monkeypatch.setattr(httpx,'get',fail)
    with pytest.raises(SearchError) as error:bing_search.fetch_html(QUERY)
    assert 'secret' not in str(error.value)


def test_db_provider_is_parameterized():
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    cursor.lastrowid=12
    assert db.insert_search_run(connection,10,'bing','bing:direct:html')==12
    assert cursor.execute.call_args.args[1]==(10,'bing','running','bing:direct:html','web')


@pytest.mark.parametrize('engine,fetcher',[('duckduckgo',None),('google','direct'),('yahoo','direct')])
def test_removed_paths_rejected(engine,fetcher):
    with pytest.raises(ValueError):get_provider(engine,fetcher)
