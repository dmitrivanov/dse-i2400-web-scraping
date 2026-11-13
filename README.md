# MY_CUSTOM_BOT

CCNY DSE I2400 Advanced Web Scraping project. Milestone 04 adds optional Bing screenshots
and local OCR to the existing pipeline, which supports Google, Bing,
and DuckDuckGo through one command-line HTML → extraction → URL cleaning → MySQL ETL workflow. The original assignment
and `WebSearch_Google_Python_Script.py` are preserved. FastAPI still provides only
`/`, `/health`, and `/db-health`; no search API or GUI is included.

## Milestone 05: functional web search interface

Start the local application and open **http://127.0.0.1:8765/search**:

```sh
cd "/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project"
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

The page at `/search` is the responsive HTML/CSS/JavaScript interface. Existing `/`,
`/health` and `/db-health` JSON endpoints are preserved. There is no frontend build
system, new dependency, database migration, or second search pipeline.

The query is prefilled with `childhood cancer early diagnosis methods` and remains
editable. Bing is the initial engine; Google and DuckDuckGo are selectable. Direct
HTTP is always the web default, regardless of CLI environment configuration. ScraperAPI
is labeled paid, available only for Google, and requires explicit selection. No engine
or paid-service fallback occurs. Each submission processes just one page through
`run_search.run_search` and reads the actual committed observations back from MySQL.
The web route does not request screenshot capture; existing CLI `--capture` still works.

Results show title, destination URL, source snippet, engine, rank, ad/organic/unknown
placement and duplicate badges. Invalid URLs are marked and not linked. All observations
are shown by default; **Unique organic only** requires a valid normalized URL, known
organic placement and no duplicate flag. Organic placement does not guarantee relevance.
The diagnostic panel reports the original query, engine, fetcher, run ID/status, four
ETL counters and safe errors. Saved failed/empty runs display a warning instead of
invented results. Loading state prevents accidental duplicate submissions.

Recent history comes from the latest 20 MySQL runs. Selecting one uses a database read,
not a provider request, and does not replace the editable default query with a hidden
variation. Run 4 demonstrates the explicit prefixed query from Task 04A; no prefix is
added automatically. The original query/run/results foreign keys remain intact.

### Files and endpoints

- `static/index.html`, `styles.css`, `app.js`: accessible form labels, a responsive
  layout, run diagnostics, result cards, client-side filtering, and recent history.
  Dynamic values use DOM `textContent`, not HTML interpolation. Only validated HTTP(S)
  destinations become result links.
- `web_search.py`: explicit FastAPI routes and a small validated request model. The
  model uses Pydantic already supplied by FastAPI; no additional library is required.
- `db.py`: `get_recent_search_runs`, `get_search_run`, `get_capture_artifact` perform
  direct parameterized SQL reads and close connections/cursors. The detailed read
  returns the run and its results/artifacts from one connection snapshot.
- `main.py`: registers the web routes and mounts only the static source directory.
- `tests/test_web.py`: mocked ETL/MySQL tests for validation, engine/fetcher selection,
  database readback, history, empty/failed runs and safe artifact access. These tests
  issue no real provider requests or database writes.

| Endpoint | Purpose |
| --- | --- |
| `GET /search` | HTML interface. |
| `POST /api/search` | Validated JSON `{query, engine, fetcher}`; run one page, persist via existing ETL, read results back. |
| `GET /api/runs` | Latest 20 runs from MySQL. |
| `GET /api/runs/{run_id}` | Stored diagnostics, observations and artifact links; no external search. |
| `GET /api/artifacts/{artifact_id}/screenshot` | Database-selected PNG inside the artifacts root. |
| `GET /api/artifacts/{artifact_id}/ocr` | Database-selected UTF-8 OCR text inside the artifacts root. |

The existing schema does not store fetcher provenance. New web runs record the
non-secret fetcher choice in `artifacts/run_<id>/web_request.json`; reopen reads that
sidecar. Older CLI runs honestly display **Not recorded for this run**, rather than
inferring a fetcher. If sidecar storage fails, the completed search remains saved and
the response reports a warning. Removing/moving local sidecars loses only that metadata.

Artifact routes accept an ID and a fixed kind, never arbitrary user paths. Paths are
resolved against the controlled artifacts directory; paths outside it, traversal,
escaping symlinks, missing files and incorrect extensions return 404. Only PNG and
plain-text OCR are served, with `nosniff`; HTML/sidecars are not exposed. API artifact
metadata contains links, not absolute local filesystem paths. This is a local assignment
app without authentication; bind it to 127.0.0.1 as shown, not a public host.

Synchronous FastAPI handlers execute in its worker thread pool. Web submissions are
limited to one provider page, with existing upstream connection/operation timeouts,
no retry, no capture, and no background task infrastructure. The client stops waiting
after 90 seconds; this does not cancel a running Python operation, so refresh history
before retrying. Provider failures saved by ETL are returned with their failed run and
actual counters. Configuration/database failures use safe HTTP errors, not raw exceptions.

### Verification performed

**174 automated tests passed**, preserving all prior 146; one existing Starlette/httpx
TestClient deprecation warning remains. Command:

```sh
python -m pytest -q
```

Actual Chromium browser verification against the running FastAPI app and real MySQL:

- Interface loaded with the exact default Group B query and no JavaScript errors.
- Reopened run 1: 20 real observations; unique-organic filter showed 10.
- Reopened run 3: actual titles/URLs/snippets and correct counters; screenshot and
  OCR links both returned 200 and their stored file contents.
- Reopened failed run 2: HTTP 202/challenge warning, zero results, no provider request.
- Submitted **exactly one new live search** through the actual form, explicitly typing
  `b) Childhood cancer early diagnosis methods` with Bing/direct. MySQL run **4**
  completed with raw **10**, ads **0**, duplicates **0**, unique organic **10**.
  PAHO, ICCP and Wiley titles/snippets/destinations were visible in the interface.
- Reopened run 4: 10 stored results and persisted `direct` fetcher provenance.
- Desktop (1440px) and mobile (390px) layouts verified; no horizontal overflow.

Local ignored screenshots: `artifacts/web_verified_desktop.png` and
`artifacts/web_verified_mobile.png`. This browser verification is separate from the
mocked unit tests. No additional engine searches were performed. The 50-unique-result
requirement is still not claimed; web submissions intentionally retrieve only one page.
Google's JavaScript shell, DuckDuckGo's verification challenge, Bing query sensitivity,
and imperfect OCR remain the limitations documented in earlier milestones.

Workbench verification for the actual new web run:

```sql
USE MY_CUSTOM_BOT;
SELECT r.*, q.query_text
FROM search_runs r JOIN search_queries q ON q.id=r.query_id WHERE r.id=4;
SELECT title, original_url, normalized_url, snippet, result_rank, is_ad, is_duplicate
FROM search_results WHERE run_id=4 ORDER BY result_rank, id;
SELECT id, run_id, screenshot_path, ocr_text_path
FROM capture_artifacts WHERE run_id=3;
```

## Task 04A: Bing query discrepancy

A controlled two-request comparison preserved the complete queries end to end.
`childhood cancer early diagnosis methods` returned general childhood references;
`b) Childhood cancer early diagnosis methods` returned relevant PAHO, ICCP, Wiley
and other cancer-diagnosis results under identical HTTP settings. The latter changes
both prefix and capitalization, so their independent effects are not established.
The saved browser screenshot agrees with saved HTTP results for the unprefixed query.
No confirmed construction/parser bug was found, so retrieval behavior remains unchanged.
See [BING_DIAGNOSIS.md](BING_DIAGNOSIS.md) for the comparison, sanitized URLs, pagination
limits, and facts versus hypotheses. All 146 automated tests pass; diagnosis performed
no new database writes and no additional browser navigation.

## Milestone 04: optional rendered screenshot and OCR

```sh
cd "/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project"
source .venv/bin/activate
python -m pip install -r requirements.txt
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers"
python -m playwright install chromium
# Tesseract is a separate local executable. On macOS, if not installed:
brew install tesseract
tesseract --version
python run_search.py "childhood cancer early diagnosis methods" --engine bing --capture
python -m pytest -q
```

The Tesseract Homebrew installation was explicitly approved and completed for this
workspace's live verification (version 5.5.4, English language data). Chromium was
installed inside `.venv/playwright-browsers`, excluded by `.gitignore`. Set the export
in each new terminal when using that local browser installation. Other operating
systems need their own Tesseract installation on PATH; no auto-install occurs at runtime.

Without `--capture`, behavior is unchanged: no browser launches and no OCR runs.
Capture currently supports Bing only; selecting it with Google or DuckDuckGo fails
validation before creating records. It captures the first page even when HTML ETL
retrieves multiple pages. This is a second, independent browser navigation for the
same query; the live page may differ from the HTTP HTML observation. OCR is evidence,
not a replacement source for the existing parsed URL results.

### Modules and failure handling

- `capture_page.py`: `capture_search_page` launches Playwright Chromium, navigates
  once, checks HTTP status/final query and visible Bing organic result cards, stops
  on recognized challenges, and saves a full-page PNG. It closes the browser on
  success and failure. It never clicks verification controls, retries, spoofs a
  browser fingerprint, or changes the search retrieval code.
- `ocr_capture.py`: `extract_screenshot_text` opens the screenshot through Pillow
  (pytesseract's image dependency), invokes the local Tesseract English OCR engine
  with a 60-second timeout, and saves its actual output as UTF-8. Empty output is
  reported as a failure; no OCR content is fabricated.
- `run_search.capture_run` orchestrates these optional steps only after successful
  HTML ETL has committed valid organic results. It creates a fresh
  `artifacts/run_<id>/capture_<uuid>/` directory with `search_results.png` and
  `ocr.txt`. UUID directories and overwrite checks preserve existing captures.
- `db.insert_capture_artifact` inserts paths with parameterized SQL into the existing
  `capture_artifacts` table and links them by `run_id`. There is no new table or schema
  migration. Files use absolute local paths, so moving the project requires updating
  those metadata paths deliberately.

Playwright is needed to render the page; pytesseract is a thin interface to a separately
installed Tesseract executable; Pillow loads the PNG. Tests mock browser, OCR and
MySQL boundaries to verify file creation, UTF-8 content, foreign-key arguments,
transaction rollback, optional invocation, and failure isolation.

Capture metadata has its own transaction. If OCR fails, the screenshot path is saved
with `ocr_text_path=NULL` and a clear CLI error. If screenshot capture fails, no
artifact metadata is inserted. If metadata storage fails, that transaction rolls back
and local files are retained for inspection. Search-run status/counts and previously
stored observations are not rolled back by a capture failure. The CLI exits nonzero
for requested capture failure, partial OCR success, or skipped capture; its summary
reports search and capture status separately. Capture is skipped when HTML ETL fails
or returns no valid organic URLs. English OCR can misread icons, punctuation, URLs,
and small text; no OCR accuracy percentage is inferred from a single screenshot.

### Actual live verification

Executed the exact Group B CLI command above with `--engine bing --capture`:

- Search run **3**: completed; raw **10**, ads **0**, duplicates **0**, final **10**.
- Capture artifact **1**: both paths persisted, joined to Bing run 3 and its original
  Group B query. Read-back verified both files exist on disk.
- Screenshot: **1440 × 1884**, visually inspected; contains the assigned query and ten
  rendered Bing result cards, not a consent/CAPTCHA page or a mocked HTML rendering.
- OCR: **2,445 UTF-8 characters**, including the exact assigned query, result titles,
  and snippets. Several domain names, slash characters and icons were misrecognized;
  the text is useful for auditing but should not be used as authoritative URLs.
- The page still contains broad childhood dictionary/encyclopedia references. Capture
  success does not make those sources relevant to early cancer diagnosis.
- Prior run 1 retains **20 observations**; run 3 has **10 new observations**. Existing
  results and captures were not overwritten. The 50-unique-URL target remains unmet.

The live paths are under
`artifacts/run_3/capture_f82b493febd74769a8bcc0448bddcae5/`.
All generated files remain ignored by Git. Automated suite: **139 tests passed**
(including the prior 119); one existing Starlette/httpx deprecation warning remains.
Live screenshot/OCR/database verification was performed separately from mocked tests.

Workbench queries:

```sql
USE MY_CUSTOM_BOT;
SELECT c.id AS artifact_id, c.run_id, r.engine, r.status, q.query_text,
       c.screenshot_path, c.ocr_text_path, c.created_at
FROM capture_artifacts c
JOIN search_runs r ON r.id = c.run_id
JOIN search_queries q ON q.id = r.query_id
WHERE c.run_id = 3;

SELECT run_id, COUNT(*) AS stored_observations
FROM search_results WHERE run_id IN (1, 3)
GROUP BY run_id;
```

The queries verify persisted metadata and preserved search observations. Open the PNG
and UTF-8 text at the stored paths to inspect the actual capture. Neither OCR text
nor image bytes are stored in MySQL.

## Milestone 03: multiple search engines

Milestone 02 was committed as an implementation milestone: `f0c3a23`
(`Milestone 02: Search ETL implementation and Google diagnostics`). Its 80 tests
passed; live Google retrieval remains limited by the observed JavaScript shell.
Task 03 authorizes committing tested engine integration even when providers have
live limitations. No commit is a claim of collecting 50 relevant research sources.

```sh
source .venv/bin/activate
python run_search.py "childhood cancer early diagnosis methods" --engine bing
python run_search.py "childhood cancer early diagnosis methods" --engine duckduckgo
python run_search.py "childhood cancer early diagnosis methods" --engine google
python run_search.py "childhood cancer early diagnosis methods" --engine google --fetcher scraperapi
python run_search.py "childhood cancer early diagnosis methods" --engine bing --max-pages 5
python -m pytest -q
```

`--engine` defaults to `google`, preserving previous commands. Google retains
`--fetcher direct|scraperapi` and `SEARCH_FETCHER` configuration. Bing and DuckDuckGo
always default to direct, independently of Google's configured fetcher. Explicit
`--fetcher scraperapi` with another engine is rejected before any database writes.
There is no automatic fallback between engines or fetchers.

### New modules and shared workflow

- `bing_search.py`: `fetch_html` retrieves one public Bing page; `parse_results`
  extracts `#b_results li.b_algo` and `li.b_ad` cards using `h2 a[href]` and
  `.b_caption p`; `next_page_start` accepts a same-query `a.sb_pagN` link's increasing
  `first` offset. No navigation or general page links are extracted.
- `duckduckgo_search.py`: retrieves the public non-JavaScript HTML interface;
  `parse_results` extracts `.result a.result__a` and `.result__snippet`. `result--ad`
  or `.result__badge--ad` marks ads; `web-result` or `results_links` is organic
  evidence; unrecognized cards retain NULL classification. Its next-page function
  accepts a same-query Next form on the HTML endpoint and preserves its hidden
  fields and GET/POST method. This pagination is fixture-tested, not live-verified.
- `run_search.py` chooses these small engine-specific functions, then uses the same
  validation, cleaning, counters, artifacts, transactions and failure handling as
  Google. `db.insert_search_run` now receives the selected engine as a parameter;
  no table definitions were changed in Milestone 03.
- `clean_urls.py` additionally decodes recognized Bing `/ck/a?u=a1...` base64 URL
  wrappers and DuckDuckGo `/l/?uddg=...` wrappers locally. Unknown/invalid wrappers
  remain invalid rather than triggering another request. Raw original URLs remain
  stored. Deduplication is within each run; observations across engines are retained.
- `tests/test_engines.py` tests parsing, encoded queries, blocked/network responses,
  pagination, engine selection, database arguments, failure status, shared ETL and
  cross-engine URL equivalence. Bing's fixture is sanitized from the live response;
  DuckDuckGo's fixture is explicitly synthetic and is never inserted into MySQL.

No new library was added. Direct requests use honest project identification, bounded
10-second connect / 30-second operation timeouts, no retries, and report HTTP redirects
without following them. CAPTCHA/challenge markup or missing result cards fails parsing.
The bounded page limit remains five, with a two-second pause between pages. Pagination
uses observed next links/forms only and increasing offsets no larger than 100. It stops
at 50 final URLs, exhausted pagination, a block, or the page limit. To evaluate a combined
collection, use the exact distinct-URL query below rather than adding per-engine counts.

### Actual live verification

Group B query: `childhood cancer early diagnosis methods`.

| Engine | Live HTTP responses | MySQL run | Status | Raw | Ads | Duplicates | Final |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Bing | 200, 200 | 1 | completed | 20 | 0 | 10 | 10 |
| DuckDuckGo | 202 human-verification challenge | 2 | failed | 0 | 0 | 0 | 0 |
| Google | Not requested in Task 03 | — | Previous JavaScript shell limitation remains | — | — | — | — |

There were **three network requests total**: Bing's initial page, its next page, and
one DuckDuckGo request. The initial captured Bing HTML was reused for the first ETL
page without requesting it again. The next page returned the same ten URLs; no further
valid next link was available. DuckDuckGo's observed failure was recorded without a
second request. MySQL read-back confirmed run 1 has 20 stored observations and run 2
has none, with each run joined to its original Group B query through foreign keys.
Combined unique organic count for these two runs: **10**. The 50-URL target was **not
achieved**. Several Bing results were broad childhood references (including dictionary
and encyclopedia entries), despite the full query being present in the response's
query field. Organic classification measures placement, not medical relevance; these
are not claimed as 10 relevant early-diagnosis research sources.

Local ignored evidence: `artifacts/bing_diagnostic.html`,
`artifacts/duckduckgo_diagnostic.html`, `artifacts/run_1/page_1.html`,
`artifacts/run_1/page_2.html`, and `artifacts/milestone03_verification.json`.
Automated verification: **119 tests passed**, including all original 80 tests.
One existing Starlette/httpx TestClient deprecation warning remains.

### Workbench verification and cross-engine comparison

```sql
USE MY_CUSTOM_BOT;
SELECT r.id, r.query_id, q.query_text, r.engine, r.status,
       r.raw_count, r.ad_count, r.duplicate_count, r.final_count, r.error_message
FROM search_runs r JOIN search_queries q ON q.id = r.query_id
WHERE r.id IN (1, 2)
ORDER BY r.id;

SELECT r.engine, s.*
FROM search_results s JOIN search_runs r ON r.id = s.run_id
WHERE r.id IN (1, 2)
ORDER BY s.run_id, s.result_rank;

SELECT r.engine, s.title, s.original_url, s.normalized_url
FROM search_results s JOIN search_runs r ON r.id = s.run_id
WHERE r.id IN (1, 2) AND s.normalized_url IS NOT NULL
  AND s.is_ad = FALSE AND s.is_duplicate = FALSE
ORDER BY s.run_id, s.result_rank;

-- Replace (1, 2) with the chosen cohort of runs for the SAME query.
-- Binary comparison preserves URL path/query case unlike the default DB collation.
SELECT COUNT(DISTINCT CAST(s.normalized_url AS BINARY)) AS combined_unique_urls
FROM search_results s JOIN search_runs r ON r.id = s.run_id
WHERE r.id IN (1, 2) AND s.normalized_url IS NOT NULL
  AND s.is_ad = FALSE AND s.is_duplicate = FALSE;

SELECT MIN(s.normalized_url) AS normalized_url,
       GROUP_CONCAT(DISTINCT r.engine ORDER BY r.engine) AS engines,
       COUNT(*) AS observations
FROM search_results s JOIN search_runs r ON r.id = s.run_id
WHERE r.id IN (1, 2) AND s.normalized_url IS NOT NULL AND s.is_ad = FALSE
GROUP BY CAST(s.normalized_url AS BINARY);
```

For other runs, inspect query provenance before combining them. The example cohort
contains the actual Task 03 Group B runs; the SQL does not alter or delete records.

The prior setup and Google-specific diagnostic history follow below. Historical test
counts and provider limitations describe those earlier tasks.

## Setup

Prerequisites: Python 3.10+, MySQL 8.0.16+, and MySQL Workbench. Direct retrieval needs no API key. ScraperAPI is optional.

```sh
cd "/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Edit `.env` locally with `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and
`DB_NAME=MY_CUSTOM_BOT`. `SEARCH_FETCHER` defaults to `direct` when absent. For optional ScraperAPI access,
set `SCRAPER_API_KEY` and `SCRAPER_API_BASE_URL=https://api.scraperapi.com`.
The CLI `--fetcher` overrides `SEARCH_FETCHER`; otherwise the environment/.env value
is used. Invalid choices fail clearly. Neither method automatically falls back to the other. The copy command preserves an
existing `.env`. Process environment settings override `.env`. Never commit secrets.

In Workbench, connect to your existing local MySQL account. Choose **File → Open SQL
Script**, open `sql/schema.sql`, review it, then execute the whole script. Refresh
**Schemas → MY_CUSTOM_BOT → Tables**. This script preserves existing data but does not
migrate existing table definitions. No account or privilege changes are performed.

**Existing Milestone 01 database:** separately open and execute `sql/milestone02.sql`
in Workbench before running searches. This changes only `search_results.is_ad` to
allow NULL, preserving all existing flags and rows. NULL represents uncertain ad
classification; FALSE represents recognized organic structure. This small migration
is necessary to avoid recording uncertainty as a confident boolean. No migration
was executed automatically. MySQL DDL may commit implicitly.

Verify the nullable column with:

```sql
USE MY_CUSTOM_BOT;
SHOW TABLES;
DESCRIBE search_queries;
DESCRIBE search_runs;
DESCRIBE search_results;
DESCRIBE capture_artifacts;
DESCRIBE ai_responses;
DESCRIBE ai_summaries;
```

## Run and test

```sh
python -m pytest -q
python -c "from db import test_connection; print(test_connection())"
python -c "from db import get_table_names; print(get_table_names())"
python run_search.py "childhood cancer early diagnosis methods"
```

The assigned research topic is **Group B: Childhood cancer early diagnosis methods**.
Use that topic for examples and demonstrations. Any valid user query is supported;
the topic is not embedded in retrieval, ETL, or database code. Query/run/result foreign
keys preserve provenance. Data for other assigned groups is collected only on request.

A search writes a real query/run. Direct retrieval uses no provider credits.
ScraperAPI is selected explicitly (or through `SEARCH_FETCHER=scraperapi`) and may incur credits:

```sh
python run_search.py "childhood cancer early diagnosis methods" --fetcher direct
python run_search.py "childhood cancer early diagnosis methods" --fetcher scraperapi
```
 Start with the default
one page. Inspect the saved HTML and actual extraction before requesting more:

```sh
python run_search.py "childhood cancer early diagnosis methods" --max-pages 5
```

The limit is five requests, with two seconds between pages and no retries. Pagination
requires an explicit `#pnnext` or `rel=next` link in the returned HTML, pointing to the
same query on `https://www.google.com/search` with an increasing `start` offset no
larger than 100. Only that observed offset is used; no page is assumed to contain
50 results. Requests stop at 50 final URLs, the page limit, missing/unsupported next
links, or an error. A complete page is retained even if it takes the total above 50.
A completed run means processing succeeded, not that 50 URLs were obtained.

The query rule counts Unicode alphabetic sequences (hyphens/apostrophes split tokens),
ignoring case. At least five tokens are required after excluding this explicit list:
`a an the and or not of in on at to for with please`. Numbers do not count; repeated
words do count. This is a simple counting rule, not language understanding. Queries
longer than 1000 characters are rejected. The original query text is stored unchanged.

Start the existing JSON application separately:

```sh
python -m uvicorn main:app --reload
```

```sh
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/db-health
```

The database route returns HTTP 503 with a generic message when database configuration
or connectivity fails. The other routes need no database.

## Modules and data flow

| File / functions | Responsibility and verification |
| --- | --- |
| `config.py`: `get_database_config`, `get_scraper_config`, `get_search_fetcher` | Load and validate settings. Provider keys are restricted to the standard HTTPS endpoint. Configuration tests use isolated environment values. |
| `google_search.py`: `fetch_direct_html`, `fetch_html` | Direct HTTP is the default; optional ScraperAPI retains its original retrieval function. Both use httpx, encoded parameters, bounded timeouts, no retries, and safe errors. Direct uses an honest project User-Agent and checks recognizable challenge markup. Tests mock HTTP calls. |
| `parse_results.py`: `parse_results`, `next_page_start` | BeautifulSoup extracts linked h3 observations, supported snippets, ad classifications, and safe explicit pagination. Test with stored fixtures. |
| `clean_urls.py`: `normalize_url`, `clean_results` | Validate/normalize URLs and select duplicate representatives; deterministic URL/count tests verify behavior. |
| `run_search.py`: `validate_query`, `run_search`, `main` | Validate CLI input, orchestrate retrieval/processing, save sanitized HTML, persist results, and print real counts. Workflow tests mock MySQL and retrieval. |
| `db.py`: connection checks plus `insert_search_query`, `insert_search_run`, `insert_search_results`, `update_search_run` | Execute explicit parameterized SQL. Write helpers participate in the caller's transaction. Inspect records in Workbench. |
| `main.py` | Existing welcome, app health, and database health JSON routes. Tests mock database checks. |
| `sql/schema.sql`, `sql/milestone02.sql` | Six-table base schema and manual nullable-ad migration. |
| `tests/fixtures/`, `tests/test_search.py`, existing config/app tests | Synthetic fixtures and mocked tests; no network or real database writes during tests. |

BeautifulSoup is the only new library; it navigates HTML without a browser. httpx
was already installed for FastAPI tests and is reused for provider requests. Uvicorn
runs FastAPI, python-dotenv loads settings, mysql-connector-python executes direct
SQL, and pytest runs checks. No ORM or generic SQL abstraction is used.

The workflow commits the original query and a `running` run before retrieval. It then
fetches HTML, saves it under ignored `artifacts/run_<id>/page_<n>.html`, extracts rows,
normalizes across all pages, and commits all observations and final status together.
Failures after run creation mark it `failed` with a safe error. A later-page failure
retains observations from earlier parsed pages. Failed result transactions roll back;
a separate transaction attempts to mark the run failed with zero persisted counts.
If MySQL also rejects that failure update, the CLI reports the run ID for inspection;
the run can remain `running`. Connections/cursors close on both success and failure.

## Parser and URL rules

Selectors are **provisional until checked against actual account HTML**:

- An observation requires an `h3` inside an anchor with `href`; headings without a
  result link are skipped. Missing titles/snippets remain NULL when unsupported.
- `#tads`, `#bottomads`, or a `data-text-ad` ancestor identifies an ad.
- A `.g` result ancestor, or `.yuRUbf` inside `.MjjYud`, identifies supported organic
  structure when no recognized ad ancestor is present.
- Other linked h3 observations have `is_ad=NULL`; they are stored but excluded from
  final results. Missing ad markers can never be classified perfectly across layouts.
- Snippets use `.VwiC3b` or `.IsZvec` only; no snippet is generated.
- Recognized CAPTCHA/consent/blocked markup or no supported result headings fails
  extraction. Other changed layouts may require selector updates after inspection.

Only HTTP(S) URLs without user credentials, whitespace/control characters, invalid
ports, or unsupported host characters are valid. Protocol-relative links and Google's
`/url?q=...` / `/url?url=...` wrappers are supported. Other relative destinations are
rejected because their external origin is unknown. Recognized Google navigation
URLs are excluded. Hosts/schemes are lowercased, default ports removed, empty paths
become `/`. Parameters `utm_*`, `gclid`, `dclid`, `fbclid`, `msclkid` are removed;
other query ordering, duplicate keys, escaping, path case, and fragments are retained.
HTTP and HTTPS are distinct. The exact extracted original URL is always preserved.

## Counts and Workbench inspection

- `raw_count`: all extracted linked-heading observations, including invalid URLs,
  recognized ads, unknown placements, and duplicates.
- `ad_count`: observations explicitly classified TRUE; unknowns do not count as ads.
- `duplicate_count`: valid normalized URL observations other than their chosen
  representative. Prefer the first known organic observation, otherwise the first
  observation. An earlier ad can therefore be flagged as a duplicate of a later
  organic result. Invalid URLs are never grouped as duplicates.
- `final_count`: valid, representative observations explicitly classified FALSE.

Counters overlap: an ad can also be a duplicate. Invalid URLs have `normalized_url=NULL`;
unknown ad status has `is_ad=NULL`. Neither qualifies as final. Therefore final_count
is not simply raw minus ads minus duplicates. Results are flagged, never deleted.

Run these exact queries in a new Workbench SQL tab:

```sql
USE MY_CUSTOM_BOT;
SELECT * FROM search_queries ORDER BY id DESC LIMIT 10;
SELECT * FROM search_runs ORDER BY id DESC LIMIT 10;
SELECT * FROM search_results ORDER BY id DESC LIMIT 100;

-- Replace 123 with the chosen search_runs.id.
SET @chosen_run_id = 123;
SELECT result_rank, title, original_url, normalized_url, snippet
FROM search_results
WHERE run_id = @chosen_run_id
  AND normalized_url IS NOT NULL
  AND is_ad = FALSE
  AND is_duplicate = FALSE
ORDER BY result_rank, id;

SELECT COUNT(*) AS final_count
FROM search_results
WHERE run_id = @chosen_run_id
  AND normalized_url IS NOT NULL
  AND is_ad = FALSE
  AND is_duplicate = FALSE;

SELECT result_rank, original_url, normalized_url, is_ad, is_duplicate
FROM search_results
WHERE run_id = @chosen_run_id
ORDER BY result_rank, id;
```

`normalized_url IS NOT NULL` is the explicit validity indicator for this workflow.
NULL ad values are excluded by `is_ad = FALSE`. The six tables retain the foundation
relationships: queries parent runs/AI responses/AI summaries; runs parent results
and capture paths. InnoDB foreign keys use RESTRICT, lookup indexes support joins,
and utf8mb4 supports Unicode. AI and capture tables remain unused.

## Actual verification and remaining limits

Milestone 02B verification used **one direct request** for the Group B topic.
Google returned **HTTP 200**, but the page was a redirect shell: title `Google Search`,
zero h3 headings, three navigation/feedback links, and text asking the user to click
if not redirected. No organic results were present in the received HTML. The parser
reported exactly: `No supported linked result headings found; inspect the saved HTML`.
The local response is saved in ignored `artifacts/direct_diagnostic.html`.

No workaround, second request, paid fallback, or pagination was attempted. No ETL
records were written from that diagnostic: zero observations and zero verified organic
URLs were available; no live run counters were created. Live MySQL result persistence
remains unverified for direct retrieval. **50 organic URLs have not been achieved.**
Selectors remain provisional; there is no reason to change them based on a page with
no results. The automated redirect-shell regression test verifies HTTP 200 is insufficient.
The prior milestone confirmed the configured MySQL database contained all six tables;
the prepared nullable-ad migration is still a manual Workbench step.

Automated verification: **80 tests passed**, including direct/default/explicit fetcher
selection, absence of an API-key dependency for direct mode, encoded queries, HTTP
and network failures, recognizable challenges, parser compatibility, and existing ETL
behavior. One existing Starlette/httpx TestClient deprecation warning remains.
Tests use mocked HTTP and MySQL and never write synthetic research records.

Direct Google HTML may be a consent page, CAPTCHA, access-denied page, redirect shell,
or unsupported layout. HTTP 200 never proves extraction success. Redirects are reported
without following them; no proxies, browser impersonation, retries, or CAPTCHA bypass
are used. Direct timeouts are 10 seconds for connection and 30 seconds per network
operation; ScraperAPI keeps its 60-second operation timeout. During this task the live
request count was one (maximum authorized: three).

Task 03 explicitly authorizes committing Milestone 02 as a tested implementation
milestone, not verified live extraction. Live Google extraction/persistence remains
blocked; this commit does not claim that the 50-result requirement is met.

The standard HTML request format follows
[ScraperAPI's synchronous endpoint documentation](https://docs.scraperapi.com/synchronous-apis/using-the-api-endpoint).
Pagination follows observed links, consistent with the provider's
[pagination inspection guidance](https://www.scraperapi.com/blog/how-to-deal-with-pagination-in-python-step-by-step-guide-full-code/).
No structured SERP entitlement is assumed. No retries, CAPTCHA bypass logic,
frontend or AI integration is implemented in the historical Milestone 02 work;
Milestone 04 adds the optional screenshot/OCR feature described above.

Raw HTML artifacts are local and ignored by git. The exact API key is redacted before
HTML leaves the provider module; request URLs, headers, and raw HTTP exceptions are
never logged. Dependencies use compatible ranges rather than a lockfile. Automated
checks do not validate SQL against a real server or prove current Google markup.

## Milestone 02C: saved-response diagnosis

Inspected `artifacts/direct_diagnostic.html` without issuing another live request.
The deterministic reproduction was parsing that saved response; the original error
was `No supported linked result headings found; inspect the saved HTML`.

The document title is `Google Search`. It has zero h3 headings, zero recognized
organic/ad result containers, and three links: `/httpservice/retry/enablejs`,
`/search` (troubleshooting), and `https://support.google.com/websearch` (feedback).
There are five scripts. A zero-delay meta refresh inside `noscript` targets
`/httpservice/retry/enablejs`; request-specific tokens have been omitted here.
This is a JavaScript-required redirect shell, not genuine result HTML, and no
recognizable consent form or CAPTCHA markup was found. The parser is correctly
rejecting it rather than extracting navigation as research results.

The prior request was to `https://www.google.com/search` with the Group B query,
`hl=en` and `start=0`; its reported status was 200. The prior probe did not save
response URL/headers/history, so the exact final response URL and any server headers
cannot be verified from the artifact. `follow_redirects=False` prevented HTTP
redirect following. However, that does not explain this response: it is HTTP 200
with an HTML noscript/meta-refresh/JavaScript mechanism, not an HTTP 3xx response.
[HTTPX redirect following](https://www.python-httpx.org/quickstart/#redirection-and-history)
handles HTTP redirects; enabling it would not execute JavaScript or this HTML refresh.
No redirect handling, request headers, or search parameters were changed merely to
work around the shell. No JavaScript execution or enablejs retry was implemented.

The smallest justified change is a specific diagnostic for the observed shell when
no result observations exist:
`Google returned a JavaScript-required redirect shell; no search results`.
`tests/fixtures/google_enablejs_shell.html` is a minimized, sanitized version of the
observed structure with scripts and request tokens removed. Two regression tests
verify this classification and ensure an enablejs link cannot hide real result
observations. The new diagnostic regression failed before the change and passed
after it; replaying the original artifact now produces the same specific diagnostic.
All **80 tests passed**, preserving the original tests. One existing TestClient
Starlette/httpx deprecation warning remains.

No additional live requests or MySQL writes occurred in Task 02C. There are zero
extractable observations and no verified organic URLs in the artifact, no new run ID,
and no persisted run counters. Live normalization/deduplication/persistence cannot
be demonstrated without genuine results. The 50-URL requirement remains unmet.
At the end of Task 02C the changes were uncommitted. Task 03 now explicitly
authorizes the implementation commit while retaining these live limitations. Ordinary HTTP
access has not supplied result HTML in the observed response; parser changes cannot
recover missing results. No further request is justified by this saved evidence.
