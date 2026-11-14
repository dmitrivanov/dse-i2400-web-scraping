"""Read-only paginated Library of saved runs and unlinked historical AI outputs."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from mysql.connector import Error
import db

router = APIRouter()

# Keep retrieval identity (search_runs.provider) separate from a human provider name.
LIBRARY_SQL = """
SELECT 'run' AS kind, r.id, q.query_text,
 COALESCE(r.search_type, CASE WHEN r.engine IN ('google','bing','yahoo','duckduckgo') THEN 'web' END) AS search_type,
 CASE WHEN r.engine IN ('google','bing','yahoo','duckduckgo') OR r.search_type='ai' THEN r.engine END AS provider,
 r.started_at AS created_at,
 CASE WHEN r.search_type='ai' THEN (SELECT COUNT(*) FROM ai_responses a WHERE a.run_id=r.id)
 ELSE r.final_count END AS result_count,
 EXISTS(SELECT 1 FROM ai_summaries s WHERE s.run_id=r.id) AS summary_available
FROM search_runs r JOIN search_queries q ON q.id=r.query_id
UNION ALL
SELECT 'response', a.id, q.query_text, 'ai', a.provider, a.created_at, 1, 0
FROM ai_responses a JOIN search_queries q ON q.id=a.query_id WHERE a.run_id IS NULL
UNION ALL
SELECT 'summary', a.id, q.query_text, 'ai', NULL, a.created_at, 0, 1
FROM ai_summaries a JOIN search_queries q ON q.id=a.query_id WHERE a.run_id IS NULL
"""


def read_library(search_type: str | None, page: int, page_size: int) -> dict:
    """Fetch one bounded page plus a sentinel; never call an external provider."""
    where = "WHERE search_type=%s" if search_type else ""
    values = (search_type,) if search_type else ()
    with db.get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(f"SELECT * FROM ({LIBRARY_SQL}) saved {where} "
                           "ORDER BY created_at DESC, kind, id DESC LIMIT %s OFFSET %s",
                           values + (page_size + 1, (page - 1) * page_size))
            rows = cursor.fetchall()
    return {"items": rows[:page_size], "page": page, "has_more": len(rows) > page_size}


@router.get('/api/library')
def list_library(search_type: Literal['web', 'ai'] | None = None,
                 page: int = Query(1, ge=1, le=100000),
                 page_size: int = Query(20, ge=1, le=100)):
    try:
        return read_library(search_type, page, page_size)
    except (Error, ValueError):
        raise HTTPException(503, 'Library unavailable; check MySQL configuration') from None


@router.get('/api/library/{kind}/{item_id}')
def library_output(kind: Literal['run', 'response', 'summary'], item_id: int):
    """Read real AI texts/models, without assigning ambiguous historical run links."""
    if item_id < 1:
        raise HTTPException(422, 'Item ID must be positive')
    try:
        with db.get_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                if kind == 'run':
                    cursor.execute('SELECT id FROM search_runs WHERE id=%s', (item_id,))
                    if not cursor.fetchone():
                        raise HTTPException(404, 'Saved item not found')
                    cursor.execute('SELECT id, provider, model_name, response_text, prompt_version, created_at FROM ai_responses WHERE run_id=%s ORDER BY id', (item_id,))
                    responses = cursor.fetchall()
                    cursor.execute('SELECT id, summary_text, summarizer, created_at FROM ai_summaries WHERE run_id=%s ORDER BY id', (item_id,))
                    return {'responses': responses, 'summaries': cursor.fetchall()}
                table = 'ai_responses' if kind == 'response' else 'ai_summaries'
                fields = 'a.provider, a.model_name, a.response_text, a.prompt_version' if kind == 'response' else 'a.summary_text, a.summarizer'
                cursor.execute(f'SELECT a.id, a.created_at, q.query_text, {fields} FROM {table} a JOIN search_queries q ON q.id=a.query_id WHERE a.id=%s', (item_id,))
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(404, 'Saved item not found')
                return {'responses': [row] if kind == 'response' else [], 'summaries': [row] if kind == 'summary' else []}
    except (Error, ValueError):
        raise HTTPException(503, 'Saved output unavailable; check MySQL configuration') from None
