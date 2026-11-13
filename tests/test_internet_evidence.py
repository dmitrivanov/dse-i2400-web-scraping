"""Milestone 06 contracts: paid confirmation, SQL checkpoints, opaque URLs and capture."""
from copy import deepcopy
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

import db
import google_search
import run_search
import saved_searches
import web_search
from clean_urls import clean_results, url_evidence_counts
from main import app

QUERY = 'childhood cancer early diagnosis methods'
PROVIDER = 'google:scraperapi:structured'
client = TestClient(app)


def saved(count=54):
    return {'run': {'id':15,'query_text':QUERY,'engine':'google','provider':PROVIDER,'status':'completed',
                    'raw_count':count,'ad_count':0,'duplicate_count':0,'final_count':count},
            'results':[{'id':n+1,'run_id':15,'original_url':f'https://example.org/{n}',
                        'normalized_url':f'https://example.org/{n}','title':'Fixture','snippet':'Fixture',
                        'result_rank':n+1,'page_number':1,'is_ad':0,'is_duplicate':0} for n in range(count)],
            'artifacts':[]}


def test_cache_miss_requires_explicit_paid_authorization(monkeypatch):
    monkeypatch.setattr(run_search,'find_saved_collection',lambda *args:None)
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:pytest.fail('key read before approval'))
    monkeypatch.setattr(db,'insert_search_run',lambda *args:pytest.fail('created run before approval'))
    with pytest.raises(run_search.PaidRequestRequired,match='Authorize up to 10'):
        run_search.run_search(QUERY,mode='collect',max_pages=10)


def test_saved_collection_reused_without_approval_or_paid_request(monkeypatch):
    monkeypatch.setattr(run_search,'find_saved_collection',lambda *args:saved())
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:pytest.fail('paid configuration'))
    summary=run_search.run_search(QUERY,mode='collect')
    assert summary['reused'] and summary['final_count']==54


def test_opaque_tokens_are_observations_not_verified_destinations():
    a='https://www.google.com/goto?url=opaque-one&gsessionid=one'
    b='https://www.google.com/goto?url=opaque-two&gsessionid=two'
    rows,counts=clean_results([{'original_url':u,'is_ad':False} for u in [a,b,a,'https://example.org']],preserve_urls=True)
    assert counts['final_count']==3 and counts['duplicate_count']==1
    assert url_evidence_counts(rows)=={'direct_url_count':1,'google_redirect_count':2}
    assert rows[0]['original_url']==a and rows[0]['normalized_url']==a


def test_existing_opaque_collection_is_offered_without_forcing_spend(monkeypatch):
    data=saved(50)
    for n,row in enumerate(data['results']):row['original_url']=row['normalized_url']=f'https://www.google.com/goto?url=opaque-{n}'
    monkeypatch.setattr(db,'get_collection_candidates',lambda *args:[data['run']])
    monkeypatch.setattr(db,'get_search_run',lambda run_id:deepcopy(data))
    found=saved_searches.find_saved_collection(QUERY,'google',PROVIDER,50)
    assert found is not None
    monkeypatch.setattr(run_search,'find_saved_collection',lambda *args:found)
    monkeypatch.setattr(run_search,'get_scraper_config',lambda:pytest.fail('paid request'))
    summary=run_search.run_search(QUERY,mode='collect')
    assert summary['reused'] and summary['observed_target_met']
    assert not summary['target_met'] and summary['direct_url_count']==0


def test_api_confirmation_response_before_any_paid_call(monkeypatch):
    def needs_approval(*args,**kwargs):
        assert kwargs['allow_paid'] is False
        raise run_search.PaidRequestRequired('Authorize one paid page?')
    monkeypatch.setattr(web_search,'run_search',needs_approval)
    response=client.post('/api/search',json={'query':QUERY})
    assert response.status_code==409 and response.json()['detail']['requires_confirmation']


def test_metadata_mysql_is_authoritative_over_sidecars(monkeypatch):
    monkeypatch.setattr(saved_searches,'read_metadata',lambda *args:pytest.fail('sidecar read'))
    assert saved_searches.collection_metadata_for_run({'id':15,'collection_metadata':'{"pages":6}'})=={'pages':6}


def test_collection_metadata_parameterized_json(monkeypatch):
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    db.update_collection_metadata(connection,15,{'pages':6,'next_start':60})
    sql,args=cursor.execute.call_args.args
    assert '%s' in sql and args[1]==15 and '"pages": 6' in args[0]


def test_running_checkpoint_does_not_set_finished_timestamp():
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    db.update_search_run(connection,15,'running',{'raw_count':9,'ad_count':0,'duplicate_count':0,'final_count':9})
    assert "THEN NULL" in cursor.execute.call_args.args[0]
    assert cursor.execute.call_args.args[1][5]=='running'


def test_capture_action_uses_saved_query_not_current_form_or_paid_api(monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:saved())
    capture=MagicMock(return_value={'status':'completed','artifact_id':2})
    monkeypatch.setattr(web_search,'capture_run',capture)
    monkeypatch.setattr(web_search,'run_search',lambda *args,**kwargs:pytest.fail('search invoked by capture'))
    response=client.post('/api/runs/15/capture')
    assert response.status_code==200
    capture.assert_called_once_with(QUERY,15,engine='google')


def test_capture_failure_reported_without_claiming_image(monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:saved())
    monkeypatch.setattr(web_search,'capture_run',lambda *args,**kwargs:{'status':'failed','error':'Capture stopped at challenge'})
    data=client.post('/api/runs/15/capture').json()
    assert data['status']=='failed' and 'artifact_id' not in data


def test_missing_capture_run_is_clear(monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:None)
    assert client.post('/api/runs/999/capture').status_code==404


def test_old_opaque_collection_not_marked_fifty_publishers(monkeypatch):
    data=saved(54)
    for n,row in enumerate(data['results']):row['original_url']=row['normalized_url']=f'https://www.google.com/goto?url=opaque-{n}'
    monkeypatch.setattr(db,'get_search_run',lambda run_id:deepcopy(data))
    monkeypatch.setattr(web_search,'collection_metadata_for_run',lambda run:{})
    response=client.get('/api/runs/15').json()
    assert not response['run']['satisfies_50']
    assert response['run']['google_redirect_count']==54
    assert all(row['destination_unverified'] for row in response['results'])


def test_insert_records_keep_mysql_assigned_ids_and_page_numbers():
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    ids=iter([41,43])
    cursor.execute.side_effect=lambda *args:setattr(cursor,'lastrowid',next(ids))
    rows=saved(2)['results']
    for row in rows:row.pop('id')
    db.insert_search_results(connection,15,rows)
    assert [row['id'] for row in rows]==[41,43]
    assert all(call.args[1][0]==15 and call.args[1][-1]==1 for call in cursor.execute.call_args_list)


@pytest.mark.parametrize('value',['true',1,None])
def test_paid_authorization_requires_literal_boolean(value):
    assert client.post('/api/search',json={'query':QUERY,'allow_paid':value}).status_code==422


def test_capture_response_keeps_filesystem_paths_private(monkeypatch):
    monkeypatch.setattr(db,'get_search_run',lambda run_id:saved())
    monkeypatch.setattr(web_search,'capture_run',lambda *args,**kwargs:{'status':'completed','artifact_id':2,
                        'screenshot_path':'/private/internal/screen.png','ocr_text_path':'/private/internal/ocr.txt'})
    response=client.post('/api/runs/15/capture')
    assert response.json()=={'status':'completed','artifact_id':2}
    assert '/private' not in response.text
