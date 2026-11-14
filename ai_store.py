"""Explicit SQL persistence and cache reads for Gemini research and summaries."""
import json
from contextlib import contextmanager
from hashlib import sha256

import db


class InFlightError(Exception):
    """Another request already owns the server-scoped work lock."""


@contextmanager
def work_connection(identity: str):
    """A MySQL named lock prevents duplicate work across threads and processes."""
    name = 'ai:' + sha256(identity.encode()).hexdigest()[:60]
    with db.get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT GET_LOCK(%s, 0)', (name,))
            if cursor.fetchone()[0] != 1:
                raise InFlightError('This operation is already in progress; reopen Library after it finishes')
        try:
            yield connection
        finally:
            connection.rollback()  # also ends any failed/uncommitted read/write transaction
            with connection.cursor() as cursor:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))
                cursor.fetchone()


def cached_response(connection, query: str, model: str, version: str) -> dict | None:
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute("""SELECT a.id FROM ai_responses a
            JOIN search_runs r ON r.id=a.run_id JOIN search_queries q ON q.id=a.query_id
            WHERE CAST(q.query_text AS BINARY)=CAST(%s AS BINARY)
            AND a.provider='gemini' AND a.requested_model=%s AND a.prompt_version=%s
            AND r.status='completed' AND r.search_type='ai' AND r.engine='gemini'
            ORDER BY a.id DESC LIMIT 1""", (query, model, version))
        return cursor.fetchone()


def create_run(connection, query: str, model: str) -> tuple[int, int]:
    query_id = db.insert_search_query(connection, query)
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO search_runs (query_id,engine,provider,search_type,status,collection_metadata) VALUES (%s,'gemini','gemini','ai','running',%s)",
                       (query_id, json.dumps({'requested_model': model})))
        run_id = cursor.lastrowid
    connection.commit()
    return query_id, run_id


def save_response(connection, query_id: int, run_id: int, model: str, prompt: str, version: str, result: dict) -> int:
    """Response, source observations and completed status commit together."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ai_responses
                (query_id,run_id,provider,requested_model,model_name,response_text,prompt_text,prompt_version,grounding_metadata,usage_metadata)
                VALUES (%s,%s,'gemini',%s,%s,%s,%s,%s,%s,%s)""",
                (query_id,run_id,model,result['model'],result['text'],prompt,version,json.dumps(result['grounding']),json.dumps(result['usage'])))
            response_id = cursor.lastrowid
            for source in result['sources']:
                cursor.execute('INSERT INTO ai_sources (response_id,chunk_index,title,url) VALUES (%s,%s,%s,%s)',
                    (response_id,source['chunk_index'],source['title'],source['url']))
            cursor.execute("UPDATE search_runs SET status='completed',raw_count=%s,final_count=%s,finished_at=CURRENT_TIMESTAMP WHERE id=%s",
                           (len(result['sources']),len({s['url'] for s in result['sources']}),run_id))
        connection.commit()
        return response_id
    except Exception:
        connection.rollback()
        raise


def fail_run(connection, run_id: int, message: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("UPDATE search_runs SET status='failed',error_message=%s,finished_at=CURRENT_TIMESTAMP WHERE id=%s", (message,run_id))
    connection.commit()


def read_response(response_id: int, connection=None) -> dict | None:
    if connection is None:
        with db.get_connection() as owned:
            return read_response(response_id, owned)
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute('SELECT a.*,q.query_text FROM ai_responses a JOIN search_queries q ON q.id=a.query_id WHERE a.id=%s', (response_id,))
        response = cursor.fetchone()
        if not response:
            return None
        cursor.execute('SELECT chunk_index,title,url FROM ai_sources WHERE response_id=%s ORDER BY chunk_index', (response_id,))
        sources = cursor.fetchall()
        cursor.execute('SELECT * FROM ai_summaries WHERE source_response_id=%s ORDER BY id DESC LIMIT 1', (response_id,))
        summary = cursor.fetchone()
    return {'response': response, 'sources': sources, 'summary': summary}


def save_summary(connection, response: dict, prompt: str, version: str, result: dict) -> int:
    try:
        with connection.cursor() as cursor:
            cursor.execute('''INSERT INTO ai_summaries
                (query_id,run_id,source_response_id,summary_text,summarizer,prompt_text,prompt_version,usage_metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                (response['query_id'],response['run_id'],response['id'],result['text'],result['model'],prompt,version,json.dumps(result['usage'])))
            summary_id = cursor.lastrowid
        connection.commit()
        return summary_id
    except Exception:
        connection.rollback()
        raise


def read_summary(summary_id: int) -> dict | None:
    with db.get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute('SELECT s.*,q.query_text,a.provider AS provider FROM ai_summaries s JOIN search_queries q ON q.id=s.query_id LEFT JOIN ai_responses a ON a.id=s.source_response_id WHERE s.id=%s', (summary_id,))
            summary = cursor.fetchone()
            if not summary:
                return None
            cursor.execute('SELECT chunk_index,title,url FROM ai_sources WHERE response_id=%s ORDER BY chunk_index', (summary['source_response_id'],))
            return {'summary': summary, 'sources': cursor.fetchall()}
