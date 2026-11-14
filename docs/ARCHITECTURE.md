# Architecture after Milestone 05D

## Milestone 06 changes (current)

New collection metadata is authoritative in MySQL (`collection_metadata JSON`), with
per-page transactional checkpoints and UI polling. A cache miss requires explicit
paid authorization; the GUI can decline without issuing a provider request. Saved
Google/Bing runs have a separate explicit authentic capture/OCR action. Supplied
URLs remain unchanged; observed strings, direct addresses and opaque Google redirect
counts are reported separately. Opaque tokens are never called verified publisher
destinations. See the current README and Milestone 06 sections of the compliance and
capture audits; the following sections describe the preceding 05D baseline.

## Scope and flow

The application is a local FastAPI app, plain HTML/CSS/JavaScript, explicit MySQL SQL,
and one shared ETL. It has no ORM, task queue, frontend build, provider fallback chain,
or relevance classifier.

```text
GUI /search or CLI run_search.py
  → validate original query and explicit action/page budget
  → search_providers.get_provider(engine)
  → exact-query/provider completed-collection check
      sufficient → read MySQL; no credentials or external request needed
      missing / deliberate Refresh → provider.fetch_page(query, start)
  → supplied observations + next offset
  → URL validation and duplicate flags; attach page_number, preserve provider rank
  → parameterized MySQL insert/append + run counts in a transaction
  → read MySQL → show final URLs, diagnostics, history, and available artifacts
```

## Provider boundary

`search_providers.py` is a small dictionary, not a class hierarchy. Entries contain
(provider identity, retrieval method, fetch_page function). A page function returns
`(list_of_observation_dicts, next_offset_or_None)`. Adding an engine means implementing
that function and adding one entry; query validation, caching, transactions and GUI
serialization stay in one place. A mocked extension test verifies this seam.

- Primary `google`: `google:scraperapi:structured`, requests/JSON at exactly
  `https://api.scraperapi.com/structured/google/search/v1`, as requested in 05D.
  Original GUI text is sent under `query`, without trimming, prefixes, query rewriting
  or heuristics. `organic_results` supplies title/link/snippet/position. Other sections
  are not promoted to organic results. Provider position is not recalculated by page.
- Retained `bing`: `bing:direct:html`, explicit legacy CLI only. Its verified card
  parsing and independent Playwright capture remain. Search relevance/pagination have
  documented limitations, so it is no longer an offered GUI production choice.
- Removed: direct Google production retrieval, Google HTML parsing, failed DuckDuckGo
  production adapters, unverified paid HTML adapters and their shared transport.
  Historical database engine values remain readable. No silent substitutions occur.

The mandated `/v1` route is unit-tested but **not live-called in 05D**. Historical
run 12 verified the previous unversioned structured endpoint, not this route. Do not
interpret an audit commit or cached display as new live endpoint verification.

## Actions, reuse and credit boundaries

- **Search**: one page only if no adequate completed saved collection exists.
  Its requested minimum is one valid organic URL; a matching 9-result saved collection
  is therefore useful and offered as a no-credit result.
- **Collect 50**: explicitly selected, minimum 50 valid unique organic URLs from this
  exact query/provider in one collection. Default total budget 10 pages, configurable
  with `COLLECTION_MAX_PAGES`, bounded 1–20 and editable in the GUI/CLI. Five pages of
  nine organic rows yield only 45; six pages can yield 54. This is demonstrated with
  mocks, not purchased during this milestone.
- **Refresh**: a clearly labeled deliberate new collection, bypassing cache reuse.
  Historical results are not deleted or replaced.
- **Collect More**: explicitly append new pages to a finished, matching saved run.
  The original query must match byte-for-byte and provider identity must agree. Total
  page budget includes earlier pages. Only new observations are inserted; old IDs,
  ranks and paths are retained. Existing duplicate flags and counts are updated in the
  same append transaction. A failed database append rolls back to the prior committed
  collection; local page evidence remains for inspection.

Cache SQL uses binary equality for original query text and requires a completed run,
matching engine/provider and adequate counts. It checks actual valid unique organic
rows rather than trusting only a counter. It never merges separate partial collections
or different queries to manufacture 50. Existing 50-result resume requests require
no new key/API call. Failed runs do not qualify for ordinary cache reuse.

Provider identity is stored for new runs. Pre-column Google collections can be
recognized by their saved mapped structured JSON; direct HTML runs have no such
provenance and are not silently treated as structured collections. Unknown historical
providers remain unknown. Cache reuse does not claim freshness or topic relevance.

Google pagination sends documented `start` offsets 0,10,20,... within the page budget.
It never follows provider pagination URLs containing signed/request metadata. It stops
at ≥50 unique URLs, explicit exhaustion, empty pages, no unique progress, failure or
the budget. A successful collection can contain more than 50 because the complete last
page is retained. If a later page fails, prior pages remain with truthful failed status
and actual counts. Original rank and one-based `page_number` are separate fields.

## Persistence and schema audit

Exactly six tables remain:

| Table | Responsibility / association |
| --- | --- |
| search_queries | Original text and creation time. No rewriting or uniqueness restriction. |
| search_runs | Query FK, engine, nullable provider identity, status, counts/timing/error. |
| search_results | Run FK, original/normalized URL, title/snippet, provider rank, nullable page, ad/duplicate flags. |
| capture_artifacts | Run FK, filesystem screenshot/OCR paths; nullable paths support partial capture. |
| ai_responses | Query FK, provider/model/output columns; table exists but no integration. |
| ai_summaries | Query FK, summary/summarizer columns; table exists but no summarization. |

InnoDB, utf8mb4, BIGINT IDs, explicit RESTRICT foreign keys and FK indexes remain.
05D adds only `search_runs.provider VARCHAR(100) NULL` and
`search_results.page_number INT NULL`. Old rows retain NULL (unknown), never invented
provenance. Local migration verified all six row counts unchanged. New installations
use `sql/schema.sql`; existing installations apply `sql/milestone05d.sql` once after
checking SHOW COLUMNS. MySQL DDL commits implicitly; this is not an atomic migration.
The application does not migrate schemas at startup or drop any object.

Structured Google URLs stay exactly as supplied. `normalized_url` holds the unchanged
HTTP(S) link when valid. Deduplication is exact supplied-URL equality, not destination
resolution. Tracking variants can therefore remain distinct. Bing keeps the existing
conservative normalizer. Unknown ad flags are never counted as organic. Ads/duplicates
are excluded from final views, not destroyed from raw auditing data. MySQL BOOLEAN
values 0/1 and Python booleans are both handled by cleaning.

Capture metadata stays in SQL; image/OCR files stay on disk. AI tables can hold future
outputs, but exact summary-to-response selection/citation provenance is future work.
Table presence alone does not establish an implemented provider or summary pipeline.

## File responsibilities and dependency audit

| File/group | Role |
| --- | --- |
| main.py | Register routes/static assets; keep welcome/health checks. |
| web_search.py | Validated primary-provider controls; execute or reopen runs; safe ID-based artifact serving. |
| run_search.py | Query validation, shared cache-first ETL, refresh/append transactions, CLI and optional capture orchestration. |
| search_providers.py | Minimal Google/Bing registry and explicit supported-path validation. |
| google_search.py | requests JSON retrieval, organic mapping and Google offsets. |
| bing_search.py | Retained legacy CLI HTTP/card parsing/next-offset adapter. |
| saved_searches.py | Exact-query saved collection selection and controlled historical metadata reads. |
| clean_urls.py | Validation, duplicate flags/counts and retained legacy URL normalization. |
| db.py | Inspectable parameterized queries and caller-owned write transactions. |
| config.py, .env.example, .gitignore | Validated settings, example-only credentials and generated-data exclusion. |
| capture_page.py, ocr_capture.py | Authentic Bing screenshot and local Tesseract OCR; see CAPTURE_AUDIT.md. |
| static/index.html, styles.css, app.js | Existing design, explicit targets/budgets/actions, history and result diagnostics. |
| tests/ | Retained useful regressions plus mocked collection/cache/append and artifact safety checks. |
| tests/fixtures/ | All useful historical HTML samples retained, including failed layouts; never production search data. |
| sql/ | Base schema and additive/manual migration scripts. |
| BING_DIAGNOSIS.md | Historical evidence; not a production contract or prefix workaround. |
| WebSearch_Google_Python_Script.py | Original assignment reference demo; not imported or used by ETL. |
| DSE I2400 PROJECT  OUTLINE.docx | Local authoritative assignment rubric. |
| docs/ | Current compliance, architecture and capture audit. |

Every tracked application/test/config/static/documentation file and fixture was
inspected. Earlier duplicate provider-selection branches, separate Google HTML/JSON
handling and generic paid HTML transport are removed. No dependency is unused:
requests serves Google; httpx serves retained Bing and TestClient; BeautifulSoup
parses Bing; Playwright/pytesseract (Pillow transitively) capture/OCR; FastAPI/Uvicorn
serve the app; python-dotenv loads settings; mysql-connector-python handles SQL;
pytest runs tests. Pydantic is FastAPI's existing validation dependency. No new
framework or library was added in 05D.

Tests exclusively exercising deleted retrieval paths were removed; generic URL,
query, transaction and failure checks were retained/adapted. Baseline 207 passing
tests was recorded first. The smaller final suite is intentional, not a claim that
obsolete behavior is still supported. Historical fixtures and database rows remain.

## AI readiness — plan only, no calls or integration

Use one future small module per provider with a plain `ask(query) -> response text`
function, then a simple orchestrator inserts actual provider/model/text rows into
`ai_responses` under the original query ID. One summarization function selects explicit
saved response IDs, records which outputs it used, and inserts a real result into
`ai_summaries`. Do not assume a consumer chat subscription grants API credentials or
that a model has live web search without configuring a supported grounding capability.
A future UI would add Internet Search / AI Search modes and ID-based links to each
saved output. No AI routes, SDKs, fabricated outputs or placeholder modules are added.

| Provider | Supported programmatic route / needed access |
| --- | --- |
| OpenAI / ChatGPT | Responses API, separate OpenAI API key/account access and usage budget. See [official quickstart](https://developers.openai.com/api/docs/quickstart). |
| Gemini | Gemini API with an API key and eligible project/quota; use the documented generate-content route and separately configure grounding if needed. See [official quickstart](https://ai.google.dev/gemini-api/docs/quickstart). |
| Claude | Anthropic Messages API with API credentials and available quota. See [official API overview](https://platform.claude.com/docs/en/api/overview). |
| Microsoft Copilot | Microsoft 365 Copilot Chat API exists in preview, with licensed-user/tenant and Graph authentication/permission requirements; a CUNY consumer-facing entitlement alone does not prove API access. Confirm tenant approval. See [official Chat API overview](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/ai-services/chat/overview). |

If a provider cannot be authorized programmatically, seek instructor approval for a
manual export/import of actual labeled outputs with timestamps/source provenance.
Do not automate consumer login/challenge workflows or call another model “Copilot”.
AI readiness documentation does not establish that any credential/license is available.

## Milestone 07 presentation layer

The existing three static files now provide a monochrome centered composer,
Internet/AI presentation toggle, collapsible history and compact results. The home
screen does not automatically open a run. History uses only GET /api/runs and
GET /api/runs/{id}; active saved queries populate the composer without rewriting.
Details contains metadata and ID-based screenshot/OCR links. Mobile history is an
overlay with Escape dismissal and keyboard focus containment. Reduced motion is
respected. No frontend framework, dependency, API/schema or collection behavior changed.

AI sections are empty hidden presentation containers, shown only as an honest
unavailable state; no AI endpoints are called. Search still uses the existing
cache-first POST contract, explicit paid confirmation, per-page progress polling,
and independent capture action. tests/verify_interface.py exercises the real local
frontend with saved MySQL reads and intercepted search POSTs, including 50-card
rendering. This is a browser smoke check, not new provider-result verification.

## Milestone 08 (current)

Presentation refinements preserve the existing layout. Google alone is enabled in
Web mode; Gemini is a disabled future AI choice. Pages defaults to 1; values above
1 select the existing collection mode, bounded by the selected maximum and target50.
No new retrieval loop exists. Credit confirmation remains server-guarded. Cards hide
opaque tokens while retaining original provider hrefs. displayed_link is nullable
observation metadata, not a canonical identity or substitute URL. No website image
fetching is performed: existing artifacts capture whole SERPs, not publisher pages.

`library.py` is an isolated read-only Library module: parameterized SQL UNIONs runs
and unlinked historical AI responses/summaries, with bounded LIMIT/OFFSET pagination
and Web/AI filtering. GET /api/library returns items/page/has_more; GET
/api/library/{run|response|summary}/{id} reads stored AI text/model identifiers.
Web reopen uses the existing run detail endpoint. Output rendering uses textContent,
not HTML or model-generated markup. Library reads cannot invoke providers or capture.

Schema migration08 adds nullable run search_type, result displayed_link, and nullable
run_id FKs on AI tables; no tables dropped/recreated. New Web writes classify the run.
Known historical engine values support Web classification; unknown/null values are
retained. Existing provider retrieval identity stays intact; Library provider labels
come from known engines or explicitly AI-classified runs. Historical unlinked AI
outputs remain separate entries. Future AI writes must validate run/query consistency,
store actual model identifiers and preserve summary-to-response provenance. No AI
writes or linkage guesses are implemented now.

Source identity remains URL-based and per run, distinct conceptually from observations.
No global canonical table is justified here. Multiple runs preserve their own ranks
and snippets; cache lookup may reuse one sufficient completed exact-query/provider
run. Opaque redirects, tracking variants and possible equivalent publisher URLs remain
unresolved; distinct tokens are not verified canonical identities.

`config.get_gemini_config` and `gemini_provider.validate_configuration` only validate
server settings; no SDK import, network request or execution endpoint. Existing SDK
check found google-genai absent; defer installation until needed. The example model
is gemini-3.5-flash-lite; the existing local gemini-2.5-flash setting was preserved,
with deprecation documented in README. Grounding and model access are not live-tested.
The future flow is original query → research prompt → grounded Gemini response with
actual metadata sources → stored run-linked output → explicit Summarize → stored
summary/provenance. Provider prose alone cannot establish a citation URL.
