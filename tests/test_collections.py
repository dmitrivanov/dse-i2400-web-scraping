"""Deterministic collection/cache/provenance tests; no real API or database writes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import db
import google_search
import run_search
import saved_searches
from clean_urls import clean_results
from google_search import SearchError

QUERY = 'childhood cancer early diagnosis methods'
PROVIDER = 'google:scraperapi:structured'


def collection(count=9, query=QUERY, provider=PROVIDER, status='completed'):
    rows=[{'id':n+1,'run_id':12,'original_url':f'https://example.org/{n}',
           'normalized_url':f'https://example.org/{n}','title':'Fixture','snippet':'Fixture snippet',
           'result_rank':n+1,'page_number':1,'is_ad':0,'is_duplicate':0} for n in range(count)]
    return {'run':{'id':12,'query_text':query,'engine':'google','provider':provider,'status':status,
                   'raw_count':count,'ad_count':0,'duplicate_count':0,'final_count':count},
            'results':rows,'artifacts':[]}


@pytest.fixture
def workflow(monkeypatch,tmp_path):
    connection=MagicMock();connection.__enter__.return_value=connection
    monkeypatch.setattr(db,'get_connection',lambda:connection)
    monkeypatch.setattr(db,'insert_search_query',MagicMock(return_value=10))
    monkeypatch.setattr(db,'insert_search_run',MagicMock(return_value=20))
    save,update=MagicMock(),MagicMock()
    monkeypatch.setattr(db,'insert_search_results',save)
    monkeypatch.setattr(db,'update_search_run',update)
    monkeypatch.setattr(db,'update_result_duplicates',MagicMock())
    monkeypatch.setattr(run_search,'find_saved_collection',lambda *args:None)
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:{})
    monkeypatch.setattr(run_search,'__file__',str(tmp_path/'run_search.py'))
    monkeypatch.setattr(run_search.time,'sleep',lambda seconds:None)
    return connection,save,update


def test_completed_saved_50_requires_no_key_or_paid_calls(monkeypatch):
    saved=collection(50)
    monkeypatch.setattr(run_search,'find_saved_collection',lambda *args:deepcopy(saved))
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:pytest.fail('key read before cache'))
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:pytest.fail('paid request'))
    summary=run_search.run_search(QUERY,mode='collect')
    assert summary['reused'] is True and summary['run_id']==12 and summary['final_count']==50


def test_normal_search_reuses_partial_collection(monkeypatch):
    def find(query,engine,provider,target):
        assert (query,engine,provider,target)==(QUERY,'google',PROVIDER,1)
        return collection()
    monkeypatch.setattr(run_search,'find_saved_collection',find)
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:pytest.fail('paid request'))
    assert run_search.run_search(QUERY)['reused'] is True


def test_refresh_deliberately_bypasses_cache(workflow,monkeypatch):
    monkeypatch.setattr(run_search,'find_saved_collection',lambda *args:pytest.fail('refresh reused old data'))
    fetch=MagicMock(return_value={'organic_results':[{'title':'Fixture','link':'https://example.org/new','position':1}]})
    monkeypatch.setattr(google_search,'fetch_results',fetch)
    summary=run_search.run_search(QUERY,refresh=True)
    assert summary['reused'] is False and summary['run_id']==20
    fetch.assert_called_once()


def test_nine_results_per_page_needs_six_pages(workflow,monkeypatch):
    def fetch(query,start=0):
        return {'organic_results':[{'title':'Fixture','link':f'https://example.org/{start}-{n}','position':n+1} for n in range(9)]}
    mocked=MagicMock(side_effect=fetch)
    monkeypatch.setattr(google_search,'fetch_results',mocked)
    summary=run_search.run_search(QUERY,mode='collect',max_pages=10)
    assert summary['final_count']==54 and summary['pages']==6
    assert [call.kwargs['start'] for call in mocked.call_args_list]==[0,10,20,30,40,50]
    rows=workflow[1].call_args.args[2]
    assert rows[-1]['page_number']==6 and rows[-1]['result_rank']==9
    assert all(row['is_ad'] is False for row in rows)


def test_five_pages_cannot_guarantee_fifty(workflow,monkeypatch):
    monkeypatch.setattr(google_search,'fetch_results',lambda query,start=0:{'organic_results':[{'link':f'https://example.org/{start}-{n}'} for n in range(9)]})
    summary=run_search.run_search(QUERY,mode='collect',max_pages=5)
    assert summary['final_count']==45 and summary['pages']==5


def test_collect_more_appends_without_reinserting_existing_rows(workflow,monkeypatch):
    saved=collection()
    monkeypatch.setattr(db,'get_search_run',lambda run_id:deepcopy(saved))
    monkeypatch.setattr(run_search,'read_metadata',lambda *args:{'pages':1,'next_start':10})
    fetch=MagicMock(return_value={'organic_results':[{'link':'https://example.org/extra','position':2}], 'pagination':{'next_page_url':None}})
    monkeypatch.setattr(google_search,'fetch_results',fetch)
    summary=run_search.run_search(QUERY,mode='collect',max_pages=10,resume_run_id=12)
    assert summary['run_id']==12 and summary['raw_count']==10 and summary['final_count']==10
    assert workflow[1].call_args.args[1]==12
    assert len(workflow[1].call_args.args[2])==1
    assert workflow[1].call_args.args[2][0]['page_number']==2
    fetch.assert_called_once_with(QUERY,start=10)
    db.insert_search_query.assert_not_called()
    db.insert_search_run.assert_not_called()


@pytest.mark.parametrize('different_query,different_provider',[(QUERY+' ',PROVIDER),(QUERY,'google:direct:html')])
def test_cannot_extend_unrelated_query_or_provider(workflow,monkeypatch,different_query,different_provider):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:collection(query=different_query,provider=different_provider))
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:pytest.fail('paid request'))
    with pytest.raises(ValueError,match='matching saved query/provider'):
        run_search.run_search(QUERY,mode='collect',resume_run_id=12)


def test_collect_more_rollback_preserves_prior_run(workflow,monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:collection())
    monkeypatch.setattr(run_search,'read_metadata',lambda *args:{'pages':1,'next_start':10})
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:{'organic_results':[{'link':'https://example.org/new'}]})
    workflow[1].side_effect=RuntimeError('private details')
    with pytest.raises(SearchError,match='rolled back'):
        run_search.run_search(QUERY,mode='collect',max_pages=2,resume_run_id=12)
    workflow[0].rollback.assert_called_once()
    workflow[0].commit.assert_not_called()


def test_new_run_creation_failure_rolls_back(workflow):
    db.insert_search_run.side_effect=RuntimeError('secret')
    with pytest.raises(SearchError,match='Could not create'):
        run_search.run_search(QUERY)
    workflow[0].rollback.assert_called_once()


def test_new_result_failure_marks_run_failed_without_rows(workflow,monkeypatch):
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:{'organic_results':[{'link':'https://example.org/new'}]})
    workflow[1].side_effect=RuntimeError('secret')
    with pytest.raises(SearchError,match='rolled back'):
        run_search.run_search(QUERY)
    assert workflow[2].call_args.args[2]=='failed'
    assert workflow[2].call_args.args[3]['raw_count']==0


def test_cache_does_not_combine_partial_collections(monkeypatch):
    first=collection(30);second=collection(30);second['run']['id']=13
    monkeypatch.setattr(db,'get_collection_candidates',lambda *args:[first['run'],second['run']])
    monkeypatch.setattr(db,'get_search_run',lambda run_id:first if run_id==12 else second)
    assert saved_searches.find_saved_collection(QUERY,'google',PROVIDER,50) is None


def test_cache_checks_exact_query_and_provider(monkeypatch):
    wrong=collection(50,query=QUERY+' ')
    wrong_provider=collection(50,provider='google:direct:html')
    monkeypatch.setattr(db,'get_collection_candidates',lambda *args:[wrong['run'],wrong_provider['run']])
    monkeypatch.setattr(db,'get_search_run',lambda run_id:wrong)
    assert saved_searches.find_saved_collection(QUERY,'google',PROVIDER,50) is None


def test_cache_uses_actual_unique_organic_rows_not_counter(monkeypatch):
    saved=collection(50)
    for row in saved['results']:row['original_url']='https://example.org/same'
    monkeypatch.setattr(db,'get_collection_candidates',lambda *args:[saved['run']])
    monkeypatch.setattr(db,'get_search_run',lambda run_id:saved)
    assert saved_searches.find_saved_collection(QUERY,'google',PROVIDER,50) is None


def test_historical_provider_inference_safe_and_explicit(monkeypatch,tmp_path):
    monkeypatch.setattr(saved_searches,'ARTIFACT_ROOT',tmp_path)
    run=collection()['run'];run['provider']=None
    assert saved_searches.provider_for_run(run) is None
    path=tmp_path/'run_12';path.mkdir()
    (path/'page_1.json').write_text('{"organic_results":[{"original_url":"https://example.org"}]}')
    assert saved_searches.provider_for_run(run)==PROVIDER


def test_mysql_boolean_flags_and_ads_are_not_final():
    rows=collection(2)['results']
    rows[1]['is_ad']=1
    assert clean_results(rows,preserve_urls=True)[1]['final_count']==1


@pytest.mark.parametrize('budget',[0,21,True,'10'])
def test_invalid_budgets_before_requests(budget):
    with pytest.raises(ValueError):run_search.run_search(QUERY,mode='collect',max_pages=budget)


def test_normal_search_cannot_implicitly_collect():
    with pytest.raises(ValueError,match='Normal search'):
        run_search.run_search(QUERY,max_pages=10)


def test_cache_sql_preserves_query_and_parameters(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value;cursor.fetchall.return_value=[]
    monkeypatch.setattr(db,'get_connection',lambda:connection)
    assert db.get_collection_candidates(QUERY+' ','google',50)==[]
    assert 'AS BINARY' in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1]==(QUERY+' ','google',50)


def test_collect_more_already_complete_never_spends(workflow,monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:collection(50))
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:pytest.fail('key read'))
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:pytest.fail('paid request'))
    summary=run_search.run_search(QUERY,mode='collect',resume_run_id=12)
    assert summary['reused'] is True and summary['final_count']==50


def test_resume_exhausted_pages_never_spends(workflow,monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:collection())
    monkeypatch.setattr(run_search,'read_metadata',lambda *args:{'pages':1,'next_start':None})
    monkeypatch.setattr(google_search,'fetch_results',lambda *args,**kwargs:pytest.fail('paid request'))
    with pytest.raises(ValueError,match='no further pages'):
        run_search.run_search(QUERY,mode='collect',resume_run_id=12)


def test_provider_interface_allows_extension_without_new_etl(monkeypatch,workflow):
    import search_providers
    fetch=MagicMock(return_value=([{'title':'Fixture','original_url':'https://example.org',
                                  'snippet':None,'result_rank':1,'is_ad':False}],None))
    monkeypatch.setitem(search_providers.PROVIDERS,'fixture',('fixture:direct','direct',fetch))
    summary=run_search.run_search(QUERY,engine='fixture')
    assert summary['final_count']==1 and summary['provider']=='fixture:direct'
    assert workflow[1].call_args.args[1]==20
