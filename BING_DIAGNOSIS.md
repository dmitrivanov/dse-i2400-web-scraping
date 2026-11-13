# Bing query discrepancy — Task 04A

Controlled comparison on November 13, 2026. Exactly two new live HTTP requests;
no additional browser navigation, database writes, or source changes to retrieval,
parsing, capture, normalization, or pagination.

## Findings

The complete query is preserved in outgoing requests, final response URLs, page
titles, and HTML query fields. The parser correctly extracts the returned cards.
The two exact query strings produce markedly different results under the same
HTTP method, endpoint, headers, timeout, redirect policy, and `first=1` setting.
This reproduces the user's relevant examples with query B, without injecting them.
It does not isolate the prefix's effect from capitalization: B changes both.

A = `childhood cancer early diagnosis methods`

B = `b) Childhood cancer early diagnosis methods`

“Relevant” below is a one-time human review of the ten returned titles/snippets for
an explicit childhood/pediatric cancer diagnosis, detection, or referral focus.
It is not a new classifier, page-content assessment, or clinical quality judgment.

| Query | Retrieval method | HTTP status | Final decoded query | First five titles, in order | Relevant | Complete query in HTML/image? |
| --- | --- | --- | --- | --- | --- | --- |
| A | New direct HTTP | 200 | Exactly A | CHILDHOOD Definition & Meaning - Merriam-Webster; Child development — Definition, Stages, & Facts — Britannica; CHILDHOOD — English meaning - Cambridge Dictionary; Childhood - SAGE Journals; What is Childhood ? | 0/10 | Yes: title and query field |
| B | New direct HTTP | 200 | Exactly B | Early diagnosis of cancer in children and adolescents: Interactive ...; Early Diagnosis of Childhood Cancer - paho.org; Early Diagnosis of Childhood Cancer Manual - ICCP Portal; Early Diagnosis of Childhood Cancer; Childhood Cancer Early Diagnosis and Appropriate Referral: An ... | 9/10 directly focused; 1 broader cancer detection result | Yes: title and query field |
| A | Saved run 3 HTTP | 200, previously recorded | Final response URL was not saved | CHILDHOOD Definition & Meaning - Merriam-Webster; Child development — Definition, Stages, & Facts — Britannica; What is Childhood ?; CHILDHOOD — English meaning - Cambridge Dictionary; childhood - Britannica | 0/10 | Yes: query field |
| A | Saved run 3 Playwright screenshot/OCR | 200, previously checked | Exact final URL not saved; capture code verified decoded q equals A | Same first five as saved run 3 HTTP | 0/10 | Yes: visible search box and OCR |

Both new responses contain ten valid organic cards (raw 10, ads 0, duplicates 0,
final 10 each). No new records were inserted, so there are no new run IDs.
The user-supplied browser result list is treated as reference, not a captured browser
session; its cookies, location, settings, redirect history and status are unknown.

## Sanitized query audit

New HTTP A request and final URL (no redirects followed):

```text
https://www.bing.com/search?q=childhood+cancer+early+diagnosis+methods&first=1
q decoded: childhood cancer early diagnosis methods
```

New HTTP B request and final URL (no redirects followed):

```text
https://www.bing.com/search?q=b%29+Childhood+cancer+early+diagnosis+methods&first=1
q decoded: b) Childhood cancer early diagnosis methods
```

The calls used the actual `bing_search.fetch_html` implementation, with diagnostic
interception only to inspect its httpx request and response. Both used GET,
`MY_CUSTOM_BOT/0.3 (CCNY DSE I2400 educational project)`,
`Accept-Language: en-US,en;q=0.9`, 10-second connection/30-second operation timeouts,
and no redirect following or retries. No API credentials were involved.

Pagination URL constructed by the same implementation for offset 11:

```text
https://www.bing.com/search?q=childhood+cancer+early+diagnosis+methods&first=11
q decoded: childhood cancer early diagnosis methods
```

Playwright capture URL constructed by `capture_search_page`:

```text
https://www.bing.com/search?q=childhood+cancer+early+diagnosis+methods
q decoded: childhood cancer early diagnosis methods
```

The capture uses `urlencode`, preserves the query, and checks the final host/path
and decoded q before saving. Its exact historical final URL was not persisted; it
cannot be reconstructed independently from an image. No new capture was needed:
the saved screenshot and all five first titles in its OCR match saved HTTP run 3.

## Destination comparison

Destination query strings and request/session tokens are omitted from this report.

| Rank | A destination | B destination |
| --- | --- | --- |
| 1 | `https://www.merriam-webster.com/dictionary/childhood` | `https://www.paho.org/en/documents/early-diagnosis-cancer-children-and-adolescents-interactive-quick-reference-guide` |
| 2 | `https://www.britannica.com/science/child-development-process` | `https://www.paho.org/en/documents/early-diagnosis-childhood-cancer` |
| 3 | `https://dictionary.cambridge.org/dictionary/english/childhood` | `https://www.iccp-portal.org/resources/early-diagnosis-childhood-cancer-manual` |
| 4 | `https://journals.sagepub.com/home/CHD` | `https://www.iccp-portal.org/sites/default/files/resources/Manual%20AIEPI_ENG.pdf` |
| 5 | `https://childhood.in/what-is-childhood/` | `https://onlinelibrary.wiley.com/doi/10.1002/pbc.31702` |

These are decoded returned destinations, not manually inserted sources. The broader
B result concerns non-invasive cancer detection generally; the remaining nine title/
snippet observations directly mention pediatric cancer, early diagnosis, or referral.
The comparison inspected search observations only; destination pages were not fetched.

## Pagination and interpretation

Saved run 1 page 1 and page 2 contain identical ordered normalized destination lists
and the same ten titles. Both bodies advertise `first=11` as their next link. The
pipeline stores the observations and flags ten duplicates, then stops because 11
is no longer an increasing next offset. It does not silently count them as 20 unique
results. Request construction passes the complete query and the observed offset.
The historical final pagination URL/headers were not retained; no new pagination
request was made in this task.

The next-page function carries q/first and omits additional session/navigation fields
from the link (e.g. FPIG and FORM). Whether those fields, cookies, server behavior,
or another factor explains the repeated body is unverified under this request budget.
There is no demonstrated offset-construction error to correct. Likewise, no explicit
“Showing results for”, “Including results for”, or “Search instead for” marker was
found in either new page or the saved pages. General-childhood results are observed;
Bing's internal query relaxation/rewrite is not established by those results alone.

Observed: changing from exact A to exact B changes the result set substantially;
HTTP and the saved automated browser rendering agree for A. Hypotheses about prefix
parsing, capitalization, personalization, localization, cookies or backend experiments
remain untested. No claim is made that all clients will always reproduce these results.

## Changes and verification

No confirmed application bug was found, so no automatic prefix injection, relevance
filter, parser change, pagination workaround, schema change, or new dependency was
introduced. Users can explicitly choose either valid query, including:

```sh
python run_search.py "b) Childhood cancer early diagnosis methods" --engine bing
```

This command is documented but was not executed as ETL during the diagnosis; running
it would issue a new request and create a new query/run through existing foreign keys.
The default research example remains A. A sanitized, minimized B HTML fixture retains
only observed titles/snippets/destinations and the query field, with tracking/session
fields removed. Regression tests protect exact query preservation for HTTP, offset
11, and screenshot URLs, and validate that existing selectors handle the observed B
cards. They do not assert live rankings or implement a relevance classifier.

```sh
source .venv/bin/activate
python -m pytest -q
```

Executed: **146 tests passed**, preserving all prior 139. One existing Starlette/httpx
TestClient deprecation warning remains. Raw comparison HTML and sanitized JSON evidence
are local ignored artifacts (`artifacts/bing_04a_1.html`, `bing_04a_2.html`, and
`bing_04a_comparison.json`). No secrets or generated artifacts belong in the commit.
