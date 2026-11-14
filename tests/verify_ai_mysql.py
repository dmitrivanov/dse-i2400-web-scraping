"""Opt-in integration: real MySQL SQL + mocked SDK; TEMPORARY tables only.

Run with .venv/bin/python tests/verify_ai_mysql.py (no credits).
No fixtures are inserted into permanent research tables. Closing this connection
removes its temporary tables and leaves existing data intact.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contextlib import contextmanager
import os
from unittest.mock import patch

from fastapi.testclient import TestClient
import ai_store
import db
import gemini_provider as gemini
from main import app

QUERY = 'childhood cancer early diagnosis methods'
TABLES = ['search_queries','search_runs','ai_responses','ai_summaries','ai_sources']
original_connection = db.get_connection
with original_connection() as connection:
    before = {}
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            before[table] = cursor.fetchone()[0]
            cursor.execute(f'SHOW CREATE TABLE {table}')
            definition = cursor.fetchone()[1].replace('CREATE TABLE', 'CREATE TEMPORARY TABLE', 1)
            definition = '\n'.join(line for line in definition.splitlines() if 'CONSTRAINT ' not in line).replace(',\n)', '\n)')
            assert definition.startswith('CREATE TEMPORARY TABLE')
            cursor.execute(definition)
    @contextmanager
    def temporary_connection():
        yield connection
    fixture = {'text':'## TEST FIXTURE ONLY\n\nMock research with uncertainty.',
        'model':'fixture-actual-model','grounding':{'grounding_supports':[]},
        'usage':{'total_token_count':42},'sources':[{'chunk_index':0,'title':'Fixture source','url':'https://example.org/research'}]}
    with patch.dict(os.environ, {'GEMINI_API_KEY':'fixture-not-a-real-key','GEMINI_MODEL':'gemini-2.5-flash'}), \
         patch.object(db,'get_connection',temporary_connection), \
         patch.object(gemini,'generate',return_value=fixture) as generate:
        client = TestClient(app)
        assert client.post('/api/ai/search',json={'query':QUERY}).status_code == 409
        response = client.post('/api/ai/search',json={'query':QUERY,'allow_paid':True})
        assert response.status_code == 200, response.text
        data=response.json();response_id=data['response']['id']
        assert data['response']['model_name']=='fixture-actual-model'
        assert data['sources'][0]['url']=='https://example.org/research'
        assert client.post('/api/ai/search',json={'query':QUERY}).json()['reused']
        assert generate.call_count==1
        summary = client.post(f'/api/ai/responses/{response_id}/summarize',json={'allow_paid':True})
        assert summary.status_code==200, summary.text
        summary_id=summary.json()['summary']['id']
        assert client.post(f'/api/ai/responses/{response_id}/summarize',json={}).json()['reused']
        assert generate.call_count==2
        assert client.get(f'/api/ai/responses/{response_id}').status_code==200
        assert client.get(f"/api/library/run/{data['response']['run_id']}").json()['responses'][0]['id']==response_id
        markdown=client.get(f'/api/ai/summaries/{summary_id}/export?format=markdown')
        pdf=client.get(f'/api/ai/summaries/{summary_id}/export?format=pdf')
        assert markdown.status_code==pdf.status_code==200
        assert 'Mock research' in markdown.text and pdf.content.startswith(b'%PDF')
        assert generate.call_count==2
        # Generate a long fixture PDF for visual QA, never a claimed research result.
        from summary_export import pdf_document
        export=ai_store.read_summary(summary_id)
        export['summary']['summary_text']=('# Fixture export layout check\n\n'+
            'This is a test fixture, not research evidence. Long paragraphs preserve uncertainty and wrap cleanly. '*45+'\n\n')*4
        Path('artifacts/milestone09_fixture_summary.pdf').write_bytes(pdf_document(export))
# New connection sees only permanent data; prove fixtures did not leak.
with original_connection() as connection:
    with connection.cursor() as cursor:
        for table, count in before.items():
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            assert cursor.fetchone()[0]==count
print('Temporary-MySQL AI workflow verified: research/cache/sources/summary/cache/Library/Markdown/PDF; permanent counts unchanged; zero live API calls.')
