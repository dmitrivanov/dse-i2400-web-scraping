# MY_CUSTOM_BOT

CCNY DSE I2400 Advanced Web Scraping project. Milestone 02B makes direct HTTP the default for the command-line
Google HTML → extraction → URL cleaning → MySQL ETL workflow. The original assignment
and `WebSearch_Google_Python_Script.py` are preserved. FastAPI still provides only
`/`, `/health`, and `/db-health`; no search API or GUI is included.

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
No structured SERP entitlement is assumed. No retries, CAPTCHA bypass logic, alternate
providers, frontend, AI integration, screenshots, or OCR are implemented.

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
