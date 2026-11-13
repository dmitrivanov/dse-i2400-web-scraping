# MY_CUSTOM_BOT

CCNY DSE I2400 Advanced Web Scraping. Default research topic:
`childhood cancer early diagnosis methods` (Group B). Other valid original queries
remain supported; the app never injects assignment prefixes or fabricates results.

Milestone 05D simplifies retrieval and audits the authoritative local
`DSE I2400 PROJECT  OUTLINE.docx`. This is **not a claim of full assignment completion**.

- [Assignment compliance matrix](docs/ASSIGNMENT_COMPLIANCE.md)
- [Architecture, file inventory and AI readiness](docs/ARCHITECTURE.md)
- [Screenshot/OCR audit and verified paths](docs/CAPTURE_AUDIT.md)
- [Historical Bing query investigation](BING_DIAGNOSIS.md)

## Setup

Prerequisites: Python 3.10+, MySQL 8.0.16+, MySQL Workbench. Tesseract and Playwright
Chromium are needed only for optional authentic Bing capture/OCR, not primary search.

```sh
cd "/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Edit existing `.env` locally; never overwrite/commit it. Provide DB_HOST, DB_PORT,
DB_USER, DB_PASSWORD, DB_NAME=MY_CUSTOM_BOT and SCRAPER_API_KEY. Process environment
values override dotenv values. COLLECTION_MAX_PAGES defaults to 10 and must be 1–20.
The GUI reads that default and lets the user choose an explicit total page budget.
SEARCH_FETCHER is obsolete and ignored; failed direct Google/DuckDuckGo and paid HTML
fallback choices have been removed. The primary provider is structured Google JSON.

In Workbench, connect with your existing account. For a new database, open
`sql/schema.sql`, review and execute the whole script, then refresh Schemas/Tables.
For an existing database:

1. Inspect `SHOW COLUMNS FROM search_runs; SHOW COLUMNS FROM search_results;`.
2. If needed, run `sql/milestone02.sql` once to allow unknown ad status (NULL).
3. Apply `sql/milestone05d.sql` once if `provider`/`page_number` are missing. If one
   already exists, run only the missing column statement. Never rerun ADD blindly.

05D adds nullable provider/page provenance columns only. This workspace's two additions
were applied and row counts verified unchanged. Startup never performs DDL; historical
rows retain unknown provenance/page values. All six tables and foreign keys remain.

## Run the GUI

```sh
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

Open **http://127.0.0.1:8765/search**. Keep the terminal open while using the app.
The JSON welcome route `/`, `/health`, and `/db-health` remain available. This is a
local assignment app without authentication; do not bind it publicly.

- **Search**: reuse a matching completed saved collection if available; otherwise fetch
  one page and save actual observations. A returned cache message means no paid call.
- **Collect 50**: explicitly request at least 50 valid unique organic URLs, within a
  configurable/user-controlled total budget of 1–20 pages. Default 10, not 5: nine
  organic observations per page would yield only 45 after five pages.
- **Refresh · new paid requests**: deliberately start a new run, bypassing saved reuse.
- **Collect More**: append to the selected finished Google collection only when the
  exact query/provider match. The total budget includes already collected pages.
  Existing observations/ranks are retained. Complete 50-result collections need no
  further request; exhausted or unknown page provenance is reported explicitly.

The form preserves original query text. Results show provider rank and recorded page,
plus ad/duplicate/unknown flags. The final unique-organic view is selected initially;
uncheck it to audit raw observations. History shows actual counts against the 50-URL
requirement. Recent history lists the latest 20 runs; cache lookup is not limited to that list.
Selecting a run never initiates a provider request. Existing captures/OCR
have ID-based links; structured JSON and MY_CUSTOM_BOT screenshots are not authentic
Google SERP screenshots.

The primary endpoint is exactly:
`https://api.scraperapi.com/structured/google/search/v1`.
It uses requests and JSON parsing, with the existing environment key. **No paid calls
were made in 05D**, so this mandated `/v1` route is mocked/unit-verified, not newly
live-verified. Historical Google run 12 remains accessible with nine results from the
previous unversioned structured endpoint. There is no silent fallback to that endpoint.

Google URLs remain exactly as supplied; duplicates use exact URL equality. Tracking
variants can therefore remain distinct. No redirect-resolution or relevance classifier
has been introduced. Counts describe observations and placement, not medical relevance.
Cache reuse requires one completed exact-query/provider collection meeting the count;
it never merges unrelated queries or multiple partial runs to manufacture fifty.

## CLI

```sh
# Cache-first, one-page search if no adequate saved collection exists:
python run_search.py "childhood cancer early diagnosis methods"

# Deliberate collection, with a bounded total budget:
python run_search.py "childhood cancer early diagnosis methods" --collect-50 --max-pages 10

# Explicit new paid request / new collection:
python run_search.py "childhood cancer early diagnosis methods" --refresh

# Deliberately append to an eligible saved run, not a different query:
python run_search.py "childhood cancer early diagnosis methods" --collect-50 --max-pages 10 --resume-run 12
```

No paid collection was run for this milestone. Requests stop at target, exhaustion,
empty/repeated pages, error, or budget. Previously parsed pages persist if a later page
fails. API credentials/request URLs are not logged. Existing response evidence prevents
silently re-requesting an uncommitted page after a storage failure.

Query validation requires five alphabetic tokens, ignoring case and this explicit
filler/Boolean list: `a an the and or not of in on at to for with please`. Numbers do
not count; repeats do. Hyphens/apostrophes split tokens. This is a simple documented
rule, not linguistic classification. The original stored/sent query remains unchanged.

## Optional authentic capture / legacy Bing CLI

Bing's verified CLI/capture subsystem is retained, but its inconsistent direct results
are not offered as a working GUI search choice. It uses the same provider interface,
ETL and persistence; it is not a fallback for Google.

```sh
# Optional dependencies only; Tesseract was previously installed with user approval:
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers"
python -m playwright install chromium
# macOS, only if Tesseract is missing and installation is desired:
brew install tesseract
python run_search.py "childhood cancer early diagnosis methods" --engine bing --capture
```

This explicit command captures the first original Bing SERP, runs English OCR and
stores file paths in capture_artifacts. GUI searches do not launch capture. Google
capture is unsupported and rejected. See CAPTURE_AUDIT.md for artifact 1's actual paths,
HTTP retrieval links, partial failure behavior, and realistic Google capture gaps.

## Verification

```sh
python -m pytest -q
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/db-health
curl http://127.0.0.1:8765/api/runs/12
```

Baseline: 207 tests passed before cleanup. Final count is reported in the compliance
matrix; obsolete implementation-only tests were removed and useful regressions adapted.
All pagination/50-result tests use mocks. No paid ScraperAPI or AI requests are part
of tests or 05D verification. Actual MySQL reuse was checked with HTTP calls blocked;
it returned saved run 13 without creating a run. Run 12 and capture artifact 1 remain.

Workbench:

```sql
USE MY_CUSTOM_BOT;
SHOW TABLES;
SHOW COLUMNS FROM search_runs;
SHOW COLUMNS FROM search_results;
SELECT r.*,q.query_text FROM search_runs r
JOIN search_queries q ON q.id=r.query_id WHERE r.id=12;
SELECT title,original_url,normalized_url,result_rank,page_number,is_ad,is_duplicate
FROM search_results WHERE run_id=12 ORDER BY id;
SELECT * FROM capture_artifacts WHERE id=1;
SELECT COUNT(*) AS ai_response_count FROM ai_responses;
SELECT COUNT(*) AS ai_summary_count FROM ai_summaries;
```

Remaining major assignment gaps: no verified live 50-result collection; no AI provider
execution, summarization or AI mode/output links; no authentic Google screenshot/OCR;
limited verified additional-engine coverage and no dedicated multi-engine batch command.
The requested new `/v1` route still needs an explicitly authorized future live check.
