# Gemini research, summaries and exports — Milestone 09

The implementation is verified with mocked SDK responses, browser interception, and
real MySQL SQL against connection-local temporary tables. **No live Gemini request
was made.** Account/model availability, grounding quality and quota are not yet
verified for this key. No fixture AI rows were stored in the permanent database.

## Configuration

Install the existing requirements, including official `google-genai` and ReportLab:

```sh
.venv/bin/python -m pip install -r requirements.txt
```

Set `GEMINI_API_KEY` and an explicit `GEMINI_MODEL` on the server in `.env` or process
environment. Keys never go to browser JavaScript or returned metadata. Existing
process values override dotenv. The application does not choose a different model,
project, endpoint, billing tier or key automatically.

The local model was `gemini-2.5-flash` at this audit; it was not changed. Google's
[current model documentation](https://aistudio.google.com/docs/models/gemini-2.5-flash)
marks it deprecated, limits access to existing users until December 1, 2026, and
announces provider-side automatic routing after that date. Before any live use,
review that notice and explicitly choose an available model in your account.
`.env.example` suggests the documented
[`gemini-3.5-flash-lite`](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite),
which supports Google Search grounding; this is not proof that this key has access.
No hardcoded production fallback model exists. Missing model/key produces a clear
configuration error. Cache reads do not require a key; research cache selection still
needs the requested model identifier. Summary/export reads do not need either setting.

The [official grounding guide](https://ai.google.dev/gemini-api/docs/generate-content/google-search)
documents the GenerateContent SDK API used here. At authorized execution, `models.get`
checks that this exact configured model is available to the key and supports text
generation. Grounding capability is checked by the actual request: rejection is
reported, never retried without grounding or replaced with another model.

Quota depends on project, model and tier; see [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
and [grounding pricing/terms](https://ai.google.dev/gemini-api/docs/generate-content/google-search).
A generation may perform multiple grounding queries with provider-defined charges.
We do not assert this account is free or change its billing settings. Account-specific
limits were not queried during development.

## User workflow

1. Open `/search`, choose **AI / Gemini**, and enter the original topic, for example
   `childhood cancer early diagnosis methods`.
2. Click Search. A completed exact-query/requested-model/prompt-version cache match
   opens immediately. Otherwise authorize the single research generation explicitly.
3. Read the saved research and provider-grounded source links. Missing grounding is
   stated clearly; model-written URLs are not promoted into verified source records.
4. Click **Summarize** deliberately. A saved summary for this response is reused;
   otherwise confirm one separate summary generation. Research is not rerun.
5. Download Markdown or PDF. Both export the existing saved summary, topic, creation
   date, actual model/provider when known, and the saved grounded sources. Export
   does not call Gemini. Reopen AI runs through History or Library.

No background AI calls, automatic prompt-optimization calls or automatic summaries.
The deterministic research prompt includes the exact original query and is stored
with the response. Summaries use saved text and a compact source reference list,
not full publisher pages or duplicated research prompts.

## Limits and persistence

- Official SDK timeout: 60 seconds, `HttpRetryOptions(attempts=1)` (no automatic retry).
- One generation per authorized cache miss; one model metadata GET precedes it.
- Output caps: 4096 research tokens / 1536 summary tokens. Provider thinking can consume
  part of that budget. Empty/blocked outputs fail clearly; output quality requires
  actual review and is not established by tests.
- Original queries: existing five-meaningful-word validation, at most 1000 characters.
- Summary text input: at most 24000 characters; total prompt at most 32000 characters.
  Oversized material is rejected without a generation, not silently truncated.
- MySQL named locks prevent identical in-flight research and summaries across workers.
  Keys include original query/model/prompt version, or response ID for summarization.
  Busy requests return 409. A unique nullable summary response FK is a second guard.
- Response/source/completed-run writes commit together; failed writes roll back.
  Failed research runs retain a safe error/status. No automatic retry after timeout or
  uncertain persistence: inspect Library before deliberately retrying.
- Actual model versions, prompts, grounding chunks/support associations and token usage
  are stored, never fabricated from requested model names or prose URLs.
- Search Suggestions HTML supplied by Google is displayed in a script-free sandboxed
  iframe; untrusted model text is rendered through a small DOM-based Markdown subset.
  No model HTML executes. Only links matching stored grounding URLs become clickable
  inside Markdown; the separate source list uses safe HTTP(S) URLs.
- PDF uses ReportLab's bundled Vera font and safe escaped paragraphs, page wrapping,
  numbering and actual source hyperlink annotations. Very broad Unicode scripts or
  advanced Markdown/table/math layout are not claimed; review exports for such text.

## Schema and files

Run `sql/milestone09.sql` manually after inspecting columns; never rerun ADD blindly.
It adds nullable prompt/model/grounding/usage metadata to `ai_responses`, nullable
source-response/prompt/usage provenance to `ai_summaries`, and one `ai_sources` table
linked to actual responses with original grounding chunk indices. Historical AI rows
remain null where provenance is unknown. Existing query/run FKs are preserved.

`gemini_provider.py` handles prompts and SDK extraction; `ai_store.py` handles explicit
SQL/transactions/cache/locks; `ai_routes.py` handles authorization and saved APIs;
`summary_export.py` creates exports from saved data; `static/ai.js` handles AI display.
No ORM, task queue, model-switching framework or second Web ETL was introduced.

## One controlled live test — only when the owner chooses to authorize it

1. Review current Gemini model availability, grounding support and project quotas in
   AI Studio. Explicitly set `GEMINI_MODEL` to that model in `.env`; keep the key local.
   Restart Uvicorn if necessary. Do not rely on a deprecated model's future aliasing.
2. Run `.venv/bin/python -c 'from gemini_provider import validate_configuration; print(validate_configuration())'`.
   This validates locally and makes no API call. It does not prove account access.
3. Open the local UI, choose AI/Gemini, enter the Group B query, and click Search.
   Review the confirmation, then authorize **one** research request. If cached, no
   request is necessary. Do not click Refresh or automatically repeat failures.
4. Check actual response, source links, actual model in Details and the saved Library
   entry. Missing grounding or quota/model rejection must be reported as observed.
5. Reopen the saved response to prove no request occurs. Stop there for a one-call
   test. Summarize is a separate optional generation and needs its own authorization.

Automated/offline commands:

```sh
.venv/bin/python -m pytest -q
PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers" .venv/bin/python tests/verify_layout.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers" .venv/bin/python tests/verify_interface.py
PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers" .venv/bin/python tests/verify_ai_interface.py
.venv/bin/python tests/verify_ai_mysql.py
```

The browser scripts need the local app; the MySQL integration script uses temporary
table copies (columns/indexes, without unsupported temporary FKs). Permanent table
counts are checked unchanged on a new connection. Fixture PDFs/screenshots are
ignored under artifacts/ and are not authentic research outputs or Google screenshots.
