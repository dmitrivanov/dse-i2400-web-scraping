"""Cache-first AI research, explicit summarization and saved exports."""
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, HTMLResponse
from mysql.connector import Error
from pydantic import BaseModel, Field, model_validator

import ai_store
import db
import gemini_provider as gemini
from config import get_gemini_model
from run_search import validate_query
from summary_export import markdown_document, pdf_document

router = APIRouter()


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    allow_paid: bool = Field(default=False, strict=True)

    @model_validator(mode='after')
    def validate_topic(self):
        validate_query(self.query)
        return self


class Authorization(BaseModel):
    allow_paid: bool = Field(default=False, strict=True)


def require_authorization(allowed: bool, operation: str) -> None:
    if not allowed:
        raise HTTPException(409, {'requires_confirmation': True,
            'message': f'Authorize one Gemini {operation} request? Usage and grounding may incur charges.'})


def read_packet(response_id: int) -> dict:
    data = ai_store.read_response(response_id)
    if not data:
        raise HTTPException(404, 'AI response not found')
    # Prompt/token metadata is accessed through Details only; no secrets are stored.
    return data


@router.post('/api/ai/search')
def research(request: ResearchRequest):
    try:
        model = get_gemini_model()
        with ai_store.work_connection(f'research:{model}:{gemini.RESEARCH_VERSION}:{request.query}') as connection:
            saved = ai_store.cached_response(connection, request.query, model, gemini.RESEARCH_VERSION)
            if saved:
                return {**read_packet(saved['id']), 'reused': True}
            require_authorization(request.allow_paid, 'research')
            # Validate key before creating any run; no external call yet.
            gemini.validate_configuration()
            query_id, run_id = ai_store.create_run(connection, request.query, model)
            prompt = gemini.research_prompt(request.query)
            try:
                result = gemini.generate(prompt, True, model)
                response_id = ai_store.save_response(connection, query_id, run_id, model, prompt, gemini.RESEARCH_VERSION, result)
            except Exception as error:
                message = str(error) if isinstance(error, gemini.GeminiError) else 'AI response storage failed; no automatic retry was made'
                connection.rollback()
                ai_store.fail_run(connection, run_id, message)
                raise HTTPException(502, message) from None
        return {**read_packet(response_id), 'reused': False}
    except ai_store.InFlightError as error:
        raise HTTPException(409, str(error)) from None
    except ValueError:
        raise HTTPException(400, 'Gemini configuration is missing or invalid; check server settings') from None
    except Error:
        raise HTTPException(503, 'AI database unavailable; inspect Library before retrying') from None


@router.get('/api/ai/responses/{response_id}')
def response_detail(response_id: int):
    try:
        return read_packet(response_id)
    except (Error, ValueError):
        raise HTTPException(503, 'AI database unavailable') from None


@router.post('/api/ai/responses/{response_id}/summarize')
def summarize(response_id: int, request: Authorization):
    try:
        with ai_store.work_connection(f'summary:{response_id}') as connection:
            data = ai_store.read_response(response_id, connection)
            if not data:
                raise HTTPException(404, 'AI response not found')
            if data['summary'] and data['summary']['summary_text'].strip():
                return {**data, 'reused': True}
            response = data['response']
            if response['provider'] != 'gemini' or not response['run_id']:
                raise HTTPException(400, 'Only run-linked Gemini research can be summarized')
            require_authorization(request.allow_paid, 'summary')
            model = get_gemini_model()
            prompt = gemini.summary_prompt(response['response_text'], data['sources'])
            result = gemini.generate(prompt, False, model)
            ai_store.save_summary(connection, response, prompt, gemini.SUMMARY_VERSION, result)
        return {**read_packet(response_id), 'reused': False}
    except ai_store.InFlightError as error:
        raise HTTPException(409, str(error)) from None
    except gemini.GeminiError as error:
        raise HTTPException(502, str(error)) from None
    except ValueError:
        raise HTTPException(400, 'Gemini configuration is missing or invalid; check server settings') from None
    except Error:
        raise HTTPException(503, 'AI summary database unavailable; inspect saved output before retrying') from None


@router.get('/api/ai/summaries/{summary_id}/export')
def export_summary(summary_id: int, format: Literal['markdown', 'pdf'] = 'markdown'):
    try:
        data = ai_store.read_summary(summary_id)
        if not data:
            raise HTTPException(404, 'Saved summary not found')
        content = markdown_document(data).encode('utf-8') if format == 'markdown' else pdf_document(data)
        extension = 'md' if format == 'markdown' else 'pdf'
        return Response(content, media_type='text/markdown; charset=utf-8' if format == 'markdown' else 'application/pdf',
            headers={'Content-Disposition': f'attachment; filename="research-summary-{summary_id}.{extension}"', 'X-Content-Type-Options': 'nosniff'})
    except (Error, ValueError):
        raise HTTPException(503, 'Saved summary export unavailable') from None


@router.get('/api/ai/responses/{response_id}/suggestions')
def grounding_suggestions(response_id: int):
    """Provider Search Suggestions live in an isolated, script-free iframe."""
    data = response_detail(response_id)
    value = data['response'].get('grounding_metadata') or {}
    if isinstance(value, str):
        value = json.loads(value)
    markup = (value.get('search_entry_point') or {}).get('rendered_content', '')
    return HTMLResponse(markup, headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; sandbox allow-popups allow-popups-to-escape-sandbox", 'X-Content-Type-Options': 'nosniff'})
