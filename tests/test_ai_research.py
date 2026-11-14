"""AI tests use fake SDK responses and mocked persistence only: no API credits."""
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import MagicMock
import re

import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import types

import ai_routes
import ai_store
import config
import gemini_provider as gemini
from main import app
from summary_export import markdown_document, pdf_document

QUERY = 'childhood cancer early diagnosis methods'
MODEL = 'gemini-2.5-flash'
client = TestClient(app)


def payload():
    return {'model_version':'actual-model-version', 'candidates':[{'finish_reason':'STOP',
        'content':{'parts':[{'text':'## Findings\n\nFixture only. [1]'}, {'text':'private thought','thought':True}]},
        'grounding_metadata': {'grounding_chunks':[{'web':{'title':'Fixture source','uri':'https://example.org/paper'}},
            {'web':{'uri':'javascript:bad'}}, {'web':{'uri':'https://user:pass@example.org'}}],
            'grounding_supports':[{'segment':{'text':'Fixture only.'},'grounding_chunk_indices':[0]}]}}],
        'usage_metadata':{'prompt_token_count':15,'candidates_token_count':20,'total_token_count':35}}


def packet(summary=None):
    return {'response':{'id':1,'run_id':10,'query_id':5,'query_text':QUERY,'provider':'gemini',
             'requested_model':MODEL,'model_name':'actual-model-version','response_text':'Fixture response',
             'prompt_version':gemini.RESEARCH_VERSION,'created_at':'2026-11-13T12:00:00'},
            'sources':[{'chunk_index':0,'title':'Fixture source','url':'https://example.org/paper'}], 'summary':summary}


@pytest.fixture
def workflow(monkeypatch):
    connection = MagicMock()
    @contextmanager
    def locked(identity):
        yield connection
    monkeypatch.setattr(ai_store,'work_connection',locked)
    monkeypatch.setattr(ai_store,'cached_response',MagicMock(return_value=None))
    monkeypatch.setattr(ai_store,'create_run',MagicMock(return_value=(5,10)))
    monkeypatch.setattr(ai_store,'save_response',MagicMock(return_value=1))
    monkeypatch.setattr(ai_store,'save_summary',MagicMock(return_value=2))
    monkeypatch.setattr(ai_store,'fail_run',MagicMock())
    monkeypatch.setattr(ai_store,'read_response',MagicMock(return_value=packet()))
    monkeypatch.setattr(ai_routes,'get_gemini_model',lambda:MODEL)
    monkeypatch.setattr(gemini,'validate_configuration',lambda:{})
    generate = MagicMock(return_value=gemini.extract_response(payload()))
    monkeypatch.setattr(gemini,'generate',generate)
    return connection,generate


def test_deterministic_prompt_preserves_exact_query():
    exact='  Childhood cancer early diagnosis methods “referral”  '
    assert f'<topic>{exact}</topic>' in gemini.research_prompt(exact)
    assert gemini.research_prompt(exact)==gemini.research_prompt(exact)


def test_grounding_sources_and_citations_are_provider_metadata():
    result=gemini.extract_response(payload())
    assert result['sources']==[{'chunk_index':0,'title':'Fixture source','url':'https://example.org/paper'}]
    assert result['model']=='actual-model-version'
    assert result['usage']['total_token_count']==35
    assert 'private thought' not in result['text']
    assert result['grounding']['grounding_supports'][0]['grounding_chunk_indices']==[0]


def test_no_grounding_does_not_invent_sources():
    data=payload();data['candidates'][0].pop('grounding_metadata')
    data['candidates'][0]['content']['parts']=[{'text':'A model-written URL https://example.org'}]
    assert gemini.extract_response(data)['sources']==[]


@pytest.mark.parametrize('data',[{}, {'candidates':[{'content':{'parts':[]}}]}])
def test_empty_or_blocked_output_is_clear(data):
    with pytest.raises(gemini.GeminiError):gemini.extract_response(data)


def test_search_requires_confirmation_before_generation(workflow):
    response=client.post('/api/ai/search',json={'query':QUERY})
    assert response.status_code==409 and response.json()['detail']['requires_confirmation']
    workflow[1].assert_not_called();ai_store.create_run.assert_not_called()


def test_research_persists_actual_response_and_prompt(workflow):
    response=client.post('/api/ai/search',json={'query':QUERY,'allow_paid':True})
    assert response.status_code==200
    workflow[1].assert_called_once_with(gemini.research_prompt(QUERY),True,MODEL)
    args=ai_store.save_response.call_args.args
    assert args[1:6]==(5,10,MODEL,gemini.research_prompt(QUERY),gemini.RESEARCH_VERSION)
    assert args[6]['model']=='actual-model-version'
    assert response.json()['reused'] is False


def test_cache_does_not_require_key_or_call_provider(workflow,monkeypatch):
    ai_store.cached_response.return_value={'id':1}
    monkeypatch.setattr(gemini,'validate_configuration',lambda:pytest.fail('cache read required key'))
    result=client.post('/api/ai/search',json={'query':QUERY}).json()
    assert result['reused'] is True
    workflow[1].assert_not_called();ai_store.create_run.assert_not_called()


def test_failed_research_retains_safe_run_status(workflow):
    workflow[1].side_effect=gemini.GeminiError('Gemini quota or rate limit reached')
    result=client.post('/api/ai/search',json={'query':QUERY,'allow_paid':True})
    assert result.status_code==502
    ai_store.fail_run.assert_called_once_with(workflow[0],10,'Gemini quota or rate limit reached')
    ai_store.save_response.assert_not_called()


def test_missing_credentials_before_run_creation(workflow,monkeypatch):
    def missing():raise ValueError('GEMINI_API_KEY is required')
    monkeypatch.setattr(gemini,'validate_configuration',missing)
    assert client.post('/api/ai/search',json={'query':QUERY,'allow_paid':True}).status_code==400
    workflow[1].assert_not_called();ai_store.create_run.assert_not_called()


def test_summary_is_separate_and_cached_without_model_settings(workflow,monkeypatch):
    data=packet({'id':2,'summary_text':'Saved summary'})
    ai_store.read_response.return_value=data
    monkeypatch.setattr(ai_routes,'get_gemini_model',lambda:pytest.fail('cached summary read model'))
    response=client.post('/api/ai/responses/1/summarize',json={})
    assert response.status_code==200 and response.json()['reused']
    workflow[1].assert_not_called();ai_store.save_summary.assert_not_called()


def test_summary_requires_confirmation_then_uses_saved_text(workflow):
    assert client.post('/api/ai/responses/1/summarize',json={}).status_code==409
    response=client.post('/api/ai/responses/1/summarize',json={'allow_paid':True})
    assert response.status_code==200
    prompt,grounded,model=workflow[1].call_args.args
    assert 'Fixture response' in prompt and grounded is False and model==MODEL
    assert prompt.count('https://example.org/paper')==1
    ai_store.save_summary.assert_called_once()
    ai_store.create_run.assert_not_called()


def test_summary_input_is_bounded():
    with pytest.raises(gemini.GeminiError):gemini.summary_prompt('x'*24001,[])
    with pytest.raises(gemini.GeminiError):gemini.summary_prompt('short',[{'chunk_index':0,'title':'x'*33000,'url':'https://example.org'}])


def test_duplicate_request_returns_conflict(workflow,monkeypatch):
    @contextmanager
    def busy(identity):
        raise ai_store.InFlightError('Already in progress')
        yield
    monkeypatch.setattr(ai_store,'work_connection',busy)
    assert client.post('/api/ai/search',json={'query':QUERY,'allow_paid':True}).status_code==409
    workflow[1].assert_not_called()


@pytest.mark.parametrize('code,word',[(429,'quota'),(403,'denied'),(404,'unavailable'),(400,'grounding'),(500,'failed')])
def test_sdk_errors_are_safe_and_not_retried(monkeypatch,code,word):
    monkeypatch.setattr(gemini,'get_gemini_config',lambda:{'api_key':'NEVER-EXPOSE','model':MODEL})
    sdk=MagicMock();sdk.__enter__.return_value=sdk
    error=Exception('NEVER-EXPOSE');error.code=code
    sdk.models.get.side_effect=error
    monkeypatch.setattr(genai,'Client',MagicMock(return_value=sdk))
    with pytest.raises(gemini.GeminiError) as failure:gemini.generate('prompt',True,MODEL)
    assert word in str(failure.value) and 'NEVER-EXPOSE' not in str(failure.value)
    sdk.models.get.assert_called_once();sdk.models.generate_content.assert_not_called()


def test_official_sdk_uses_grounding_limits_and_one_attempt(monkeypatch):
    monkeypatch.setattr(gemini,'get_gemini_config',lambda:{'api_key':'private','model':MODEL})
    sdk=MagicMock();sdk.__enter__.return_value=sdk
    sdk.models.get.return_value=types.Model(supported_actions=['generateContent'])
    sdk.models.generate_content.return_value=types.GenerateContentResponse.model_validate(payload())
    factory=MagicMock(return_value=sdk);monkeypatch.setattr(genai,'Client',factory)
    result=gemini.generate('prompt',True,MODEL)
    assert result['model']=='actual-model-version'
    options=factory.call_args.kwargs['http_options']
    assert options.timeout==60000 and options.retry_options.attempts==1
    settings=sdk.models.generate_content.call_args.kwargs['config']
    assert settings.max_output_tokens==4096 and settings.tools[0].google_search is not None
    assert settings.automatic_function_calling.disable is True
    sdk.models.generate_content.assert_called_once()


def test_mysql_lock_released_even_on_failure(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value;cursor.fetchone.return_value=(1,)
    monkeypatch.setattr(ai_store.db,'get_connection',lambda:connection)
    with pytest.raises(RuntimeError):
        with ai_store.work_connection('same-query'):raise RuntimeError('failure')
    assert 'RELEASE_LOCK' in cursor.execute.call_args.args[0]
    assert len(cursor.execute.call_args.args[1][0])<=64
    connection.rollback.assert_called_once()


def test_response_sources_and_status_commit_together():
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value;cursor.lastrowid=42
    result=gemini.extract_response(payload())
    assert ai_store.save_response(connection,5,10,MODEL,'prompt',gemini.RESEARCH_VERSION,result)==42
    statements=cursor.execute.call_args_list
    assert statements[0].args[1][3]=='actual-model-version'
    assert statements[1].args[1]==(42,0,'Fixture source','https://example.org/paper')
    connection.commit.assert_called_once()
    cursor.execute.side_effect=RuntimeError('database failure')
    with pytest.raises(RuntimeError):ai_store.save_response(connection,5,10,MODEL,'prompt','v1',result)
    connection.rollback.assert_called_once()


def test_summary_provenance_is_persisted():
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value;cursor.lastrowid=2
    ai_store.save_summary(connection,packet()['response'],'summary prompt',gemini.SUMMARY_VERSION,gemini.extract_response(payload()))
    values=cursor.execute.call_args.args[1]
    assert values[:3]==(5,10,1) and values[4:7]==('actual-model-version','summary prompt',gemini.SUMMARY_VERSION)
    connection.commit.assert_called_once()


def export_data():
    return {'summary':{'id':2,'query_text':QUERY,'summary_text':'# Findings\n\nSaved <unsafe> & text.\n\n## Conclusion\n\nUncertain findings remain uncertain.',
            'created_at':'2026-11-13T12:00:00','summarizer':'actual-model-version'},'sources':packet()['sources']}


def test_exports_use_only_saved_content(workflow,monkeypatch):
    data=export_data();monkeypatch.setattr(ai_store,'read_summary',lambda summary_id:data)
    markdown=client.get('/api/ai/summaries/2/export?format=markdown')
    pdf=client.get('/api/ai/summaries/2/export?format=pdf')
    assert data['summary']['summary_text'] in markdown.text
    assert 'https://example.org/paper' in markdown.text
    assert pdf.content.startswith(b'%PDF') and b'/URI' in pdf.content
    assert 'attachment' in pdf.headers['content-disposition']
    workflow[1].assert_not_called();ai_store.save_summary.assert_not_called()


def test_pdf_wraps_long_paragraphs_and_has_clickable_sources():
    data=export_data();data['summary']['summary_text']=('A long research finding with uncertainty. '*100+'\n\n')*5
    output=pdf_document(data)
    assert len(re.findall(rb'/Type\s*/Page\b',output))>1
    assert b'https://example.org/paper' in output


def test_suggestions_are_sandboxed(workflow):
    ai_store.read_response.return_value['response']['grounding_metadata']={'search_entry_point':{'rendered_content':'<script>bad()</script>Search'}}
    response=client.get('/api/ai/responses/1/suggestions')
    assert "default-src 'none'" in response.headers['content-security-policy']
    assert 'sandbox' in response.headers['content-security-policy']


def test_model_must_be_explicitly_configured(monkeypatch):
    monkeypatch.setattr(config,'load_dotenv',lambda *args:None)
    monkeypatch.delenv('GEMINI_MODEL',raising=False)
    with pytest.raises(ValueError,match='explicitly configured'):
        config.get_gemini_model()


def test_model_without_generation_support_is_not_called(monkeypatch):
    monkeypatch.setattr(gemini,'get_gemini_config',lambda:{'api_key':'private','model':MODEL})
    sdk=MagicMock();sdk.__enter__.return_value=sdk
    sdk.models.get.return_value=types.Model(supported_actions=['embedContent'])
    monkeypatch.setattr(genai,'Client',MagicMock(return_value=sdk))
    with pytest.raises(gemini.GeminiError,match='does not support'):
        gemini.generate('prompt',True,MODEL)
    sdk.models.generate_content.assert_not_called()


def test_sources_keep_original_indices_for_citation_associations():
    data=payload()
    data['candidates'][0]['grounding_metadata']['grounding_chunks']=[{}, {'web':{'uri':'https://example.org/source','title':'Second chunk'}}]
    assert gemini.extract_response(data)['sources'][0]['chunk_index']==1


def test_named_lock_busy_does_not_enter_work(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value=(0,)
    monkeypatch.setattr(ai_store.db,'get_connection',lambda:connection)
    with pytest.raises(ai_store.InFlightError):
        with ai_store.work_connection('same-query'):
            pytest.fail('duplicate operation entered work')
