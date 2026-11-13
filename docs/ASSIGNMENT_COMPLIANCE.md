# Assignment compliance — Milestone 05D

## Milestone 06 verification update

The Internet workflow now includes explicit paid-request confirmation after cache
lookup; atomic per-page SQL result/count/progress checkpoints; a nullable SQL JSON
collection metadata column; and an explicit saved-run Google/Bing capture action.
No new provider, scraping framework, relevance heuristic or redirect resolver was added.

Existing **run 15** supplies actual live provider evidence: **54 returned organic URL
strings**, **6 pages**, offsets **0,10,20,30,40,50**, exact Group B query, persisted
positions/page numbers, no ads and no repeated exact URLs. These rows were displayed
and cache-reused in the GUI without spending credits. Metadata is now in MySQL.
However, **47 URLs are opaque Google redirects and only 7 are direct URL addresses**.
The 54 strings are not evidence of 54 different publisher destinations. The GUI
separates these quantities and marks opaque destinations unverified. Saved data is
offered before further spend; explicit Refresh/Collect More remains deliberate.

| Requirement/update | Status | Evidence and limit |
| --- | --- | --- |
| Organic extraction, page/rank associations, deduplication, SQL persistence and display | complete | Actual saved six-page run 15 and mocked checkpoint/error tests. URLs preserved exactly. |
| 50 distinct supplied organic URL strings | complete | 54 live saved strings displayed; not a claim of distinct publisher destinations. |
| 50 distinct direct URLs / publisher destination uniqueness | unverified | 50+ direct-address collection is mocked; 47 live redirect destinations remain opaque. No network resolution was added. |
| Explicit paid consent/cache reuse | complete | Existing 54-string collection reused without authorization or paid call; deliberate Refresh prompt declined in real browser. |
| Complete collection metadata in MySQL | complete | New SQL JSON field; per-page transaction metadata; verified run 15 metadata copied to SQL from actual sidecar/evidence. |
| Authentic screenshot/OCR workflow initiated for structured Google run | partial | Explicit action implemented; live Google capture failed page/query authenticity guard, no fabricated screenshot/record. |
| Existing screenshots/OCR retrievable | complete | Bing artifact 1/run 3 image and OCR links both HTTP 200 and files exist. |

**Live status:** 54 supplied URL strings are verified from existing provider data.
**Mock-only status:** at least 50 distinct direct-address collection logic.
**Not verified:** 50 distinct publisher destinations and successful Google screenshot/OCR.
The task did not automatically purchase a full collection: **zero paid API calls**
were needed. One authentic Google browser attempt failed safely. New collection
progress/metadata persist page-by-page, and failures preserve previous committed data.

Final suite: **186 tests passed**, one existing dependency deprecation warning.
New tests cover paid authorization (strict boolean), opaque-link evidence, saved
reuse, SQL metadata/checkpoints, partial pages/failures, MySQL-assigned result IDs,
Google capture guards and retrieval. Actual browser verification displayed 54 cards,
correct counts, declined paid Refresh, working old artifact links and responsive
layout, without JavaScript errors. Original run 12 remains readable.

The 05D matrix below remains the baseline audit. AI execution, summarization, AI UI
mode/output links and broad multi-engine verification remain outside Milestone 06.
Full assignment completion is not asserted while the stated evidence gaps remain.

## Rubric and evidence boundaries

The original **DSE I2400 PROJECT  OUTLINE.docx** was available locally and read from
its Word document XML. It is the authoritative rubric, including search word rules,
ETL iteration, screenshot/OCR, four named AI providers, two GUI modes, 50 Internet URLs
and summarized AI output links. The original browser-opening Python example is a
reference, not an adequate ETL implementation.

Baseline audit: clean local main, **207 tests passed** before refactoring. All tracked
application/config/schema/static/test/fixture/documentation files were inspected.
Tests exclusive to deleted production paths were removed intentionally; useful URL,
query, error/transaction, fixture and capture tests were retained/adapted. Passing
unit tests do not prove external provider access, relevance, or full rubric compliance.

Statuses mean **complete** (implemented and supported by evidence), **partial**
(working subset), **missing** (not implemented), **unverified** (insufficient runtime
evidence). No live paid search/AI/capture was performed during 05D.

## Requirements matrix

| Requirement | Current implementation | Status | Evidence | Remaining work |
| --- | --- | --- | --- | --- |
| 1. MY_CUSTOM_BOT MySQL database | Direct connector, six InnoDB/utf8mb4 tables, no ORM. | complete | Live connection, SHOW TABLES/schema inspection, preserved row counts. | Keep setup/migrations reproducible in Workbench. |
| 2. Store queries, runs, results and AI outputs | Real search persistence and historical runs; AI tables only. | partial | Run 12/read-back; search_results; ai_responses and ai_summaries each have 0 rows and no workflow. | Implement actual AI execution and summary persistence. |
| 3. At least 4–5 meaningful words | Five-token rule excludes explicit fillers and AND/OR/NOT; exact query preserved. | complete | Query/encoding regression tests; original Group B query in MySQL. | Document that this is an explicit approximation, not NLP. |
| 4. Google and extensible additional engines | Structured requests/JSON primary; small provider dictionary; retained Bing legacy CLI. | partial | Prior unversioned Google run 12, Bing runs 1/3; new /v1 mocked; provider extension test. | Authorize live /v1 verification; verify another reliable engine path. |
| 5. Extract result URLs | Organic JSON mapping; Bing legacy cards. No fabricated observations. | complete | Run 12 has 9 persisted URLs, existing fixtures/mocked JSON, preserved returned links/ranks. | Continue testing real response changes when authorized. |
| 6. Screenshot pages and OCR | Authentic Bing Playwright capture/Tesseract, optional CLI only. | partial | Artifact 1 → run 3, PNG and OCR files exist; safe retrieval routes and capture tests. | Authentic Google capture; broader engine/page coverage, GUI capture workflow if desired. |
| 7. Remove ads and duplicate URLs | Exclude non-organic JSON sections; flags preserve raw audits; final view excludes ads/unknown/duplicates. | complete | Mocked ads/duplicates; live Bing historical duplicate observations; final eligibility tests including MySQL 0/1 flags. | URL aliases/tracking variants remain distinct by deliberate exact-link policy. |
| 8. Store cleaned URL list in MySQL | Existing result rows with validity/duplicate/ad flags define final list. | complete | Run associations, parameterized SQL, rollback and count tests; historical real rows. | No separate destructive raw-to-final table required. |
| 9. Automated ETL and iteration through engines | One provider seam/ETL for Google and retained Bing CLI. | partial | Registry extension and shared persistence tests. | Dedicated verified multi-engine orchestration/batch collection; broader engine reliability. |
| 10. ChatGPT, Gemini, Copilot, Claude outputs | No AI modules/routes/calls; schema only. | missing | ai_responses=0 and source audit; readiness plan in ARCHITECTURE.md. | Credentials/licenses/tenant authorization and actual adapters. |
| 11. Summarize/persist AI outputs | ai_summaries exists; no summary workflow. | missing | ai_summaries=0, no implementation. | Select explicit response IDs, generate real summary and persist provenance. |
| 12. Attractive Internet Search / AI Search GUI | Responsive Internet UI, history, counts, final/raw filter and safe artifact links; no AI mode. | partial | Existing browser verification and current saved-data GUI checks; static/API tests. | Add AI mode only when an actual AI pipeline is implemented. |
| 13. At least 50 Internet URLs | Explicit Collect 50, cache reuse, resume, 1–20 page budget; 54 mocked rows after 6×9. | partial | Mocked collection/duplicate/budget tests. Historical run 12 remains 9. No paid 50-result collection in this audit. | An explicitly authorized live collection and read-back/display of ≥50 actual unique organic URLs. |
| 14. AI summary with links to individual outputs | Not implemented. | missing | No AI GUI/routes/output-serving module; tables empty. | Actual summary, persisted provider outputs and safe ID-based links. |

The mandated `.../structured/google/search/v1` **live endpoint behavior is unverified**
in 05D: no credits were consumed. The successful historical run 12 used the prior
unversioned path. Code/tests use the requested new path without a silent fallback.
Cached results are not a fresh live provider test or evidence of current relevance.

## Repository simplification

Removed production modules:

- `duckduckgo_search.py`: direct challenge responses; no verified working feature.
- `parse_results.py`: obsolete Google HTML heading parsing / shell path.
- `scraper_api.py`: generic paid HTML transport no longer needed by retained paths.
- Legacy Google HTML/direct functions removed from `google_search.py`.
- Unverified paid Bing HTML helper removed; the verified direct Bing adapter remains.

Retained: main/web routes, schema/SQL, explicit database operations, requests JSON
Google, legacy CLI Bing, URL cleaning, Playwright/Tesseract, query validation, original
reference script/document, historical diagnostic document, all useful fixtures and all
historical data. Capture/OCR module implementation was not deleted or replaced with
a screenshot of reconstructed results. httpx/BeautifulSoup remain needed by Bing and
TestClient; no dependency was dropped without verifying its use. No new dependency
was introduced. Full final file/dependency inventory is in ARCHITECTURE.md.

Removed obsolete-only tests: `test_direct_search.py`; Google HTML/paid HTML/DuckDuckGo
sections of former test_search/test_engines. Generic tests moved to
`test_urls_and_query.py`; retained Bing tests stay in test_engines/test_bing_query;
new collection tests cover cache, exact matching, credit guard, append and rollback.
Historical fixtures (including failed Google/DDG layouts) remain as evidence, not
production data. Original reference files are retained but clearly not invoked by ETL.

## Data and capture verification

Two necessary nullable columns were added locally: run provider and result page_number.
No row or table was removed; pre/post counts were identical:

| Table | Rows before and after additive migration |
| --- | ---: |
| search_queries | 14 |
| search_runs | 14 |
| search_results | 118 |
| capture_artifacts | 1 |
| ai_responses | 0 |
| ai_summaries | 0 |

Old provider/page values remain NULL; inference for known old structured Google data
uses existing saved JSON rather than fabricated SQL values. Original/normalized URL,
rank, flags, foreign keys and artifact paths are preserved. New results record pages
in SQL; new runs record stable provider identity. AI table presence is not credited as
AI integration. Future summary-to-response provenance remains an identified gap.

A real MySQL cache test returned saved run **13**, with 9 results, for the exact Group
B query. requests.get was patched to fail if called; zero requests occurred and run
count stayed 14. **Run 12 remains completed with 9 results** and readable. Capture
artifact **1** still references Bing run **3**; both stored files exist. See
CAPTURE_AUDIT.md for verified paths and retrieval URLs. Raw local UI screenshots are
not labeled as provider SERP captures.

## Final verification record

- Baseline: 207 tests passed before removal of obsolete paths.
- Current suite: 166 tests passed, with one existing Starlette/httpx deprecation warning.
- Mocked coverage: exact query/provider, JSON fields, ads exclusion, unchanged URLs,
  duplicates across pages, 50+ collection, insufficient 5×9 collection, adequate saved
  reuse before key access, deliberate refresh, matching-run append, transaction errors,
  page/provider associations, retained capture/OCR and safe artifact paths.
- Actual integration: additive schema checks, table counts unchanged, cached read/reuse
  with HTTP blocked, saved run 12 and capture files available.
- Paid API/50-result/AI requests in 05D: **zero**.
- Actual Chromium read-only verification reopened run 12 and displayed 9 results and
  9/50 diagnostics; primary-only controls, explicit Collect 50 and configured ten-page
  budget were verified without submitting a search. Artifact 1 screenshot/OCR routes
  both returned HTTP 200. No browser errors, mobile overflow or POST/search requests.
  Local evidence: artifacts/milestone05d_gui.png (ignored by Git).
