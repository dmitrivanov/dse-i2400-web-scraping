# Screenshot and OCR audit

## What is implemented

`capture_page.capture_search_page(query, destination)` uses Playwright Chromium to
navigate once to `https://www.bing.com/search?q=<encoded exact query>`. It checks
HTTP 200, expected host/path/query and visible Bing organic cards, rejects recognized
CAPTCHA/challenge markup, and captures a full-page PNG. It uses an honest normal
browser session, without challenge solving, retries or a fake reconstructed SERP.
Browser cleanup occurs on success and failure.

`ocr_capture.extract_screenshot_text` opens that PNG with Pillow and runs local
Tesseract through pytesseract, English language, 60-second timeout. Actual output is
saved to UTF-8 `ocr.txt`; empty output/missing executable/errors are reported. OCR is
an audit artifact; HTML/structured result extraction remains the URL source.

Capture is **optional, CLI-only, Bing-only**, explicitly requested by:

```sh
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/playwright-browsers"
python run_search.py "childhood cancer early diagnosis methods" --engine bing --capture
```

The primary Google GUI does not launch capture automatically and does not expose an
unsupported Google capture switch. Bing's legacy CLI ETL is retained so this verified
capture workflow is not broken. It captures the first live Bing result page in a
separate navigation, not necessarily the identical response received by the HTTP
provider. Later pages are not automatically captured. Cache reuse plus explicit
`--capture` may perform this deliberate browser navigation but no paid API call.

## Storage and associations

- Directory: `<project>/artifacts/run_<id>/capture_<uuid>/`.
- Image: `search_results.png`.
- OCR: `ocr.txt` (UTF-8).
- SQL: `capture_artifacts.run_id` references `search_runs.id`; screenshot_path and
  ocr_text_path store absolute local paths. Image bytes/text stay on the filesystem.
- UUID directories and overwrite guards preserve prior artifacts.
- Metadata writes commit separately after ETL. OCR failure can save a screenshot with
  NULL OCR path. Metadata failure rolls back without corrupting saved search results;
  local files remain available for inspection. CLI reports partial/failure outcomes.

## Verified existing evidence

Capture artifact **1**, linked to Bing run **3**, was checked in MySQL during 05D.
Both existing files were present:

```text
/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project/artifacts/run_3/capture_f82b493febd74769a8bcc0448bddcae5/search_results.png
/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project/artifacts/run_3/capture_f82b493febd74769a8bcc0448bddcae5/ocr.txt
```

Historical live verification inspected a 1440×1884 genuine Bing SERP image with the
full Group B query, ten result cards and 2,445 OCR characters. The broad-childhood
result relevance problem is documented; capture authenticity does not establish
medical relevance. OCR misread some domains, slashes and icons. No accuracy score
is claimed. The files and run associations are preserved by this milestone.

## Retrieval and GUI

`GET /api/runs/3` supplies artifact-ID links, never arbitrary client path access:

- `GET /api/artifacts/1/screenshot` → image/png.
- `GET /api/artifacts/1/ocr` → text/plain UTF-8.

`web_search.artifact_file` reads the path from MySQL by ID, resolves it beneath the
controlled artifacts root, checks suffix/file existence, rejects traversal/outside
paths/escaping symlinks and serves with nosniff. Only static application source is
mounted publicly; raw HTML/JSON response directories are not static mounts. Reopen
Bing run 3 from GUI history to see its screenshot/OCR links. Historical captures
remain accessible even though Bing is no longer offered as a GUI production engine.

Workbench:

```sql
USE MY_CUSTOM_BOT;
SELECT c.id,c.run_id,r.engine,q.query_text,c.screenshot_path,c.ocr_text_path
FROM capture_artifacts c JOIN search_runs r ON r.id=c.run_id
JOIN search_queries q ON q.id=r.query_id WHERE c.id=1;
```

## Google limitation and compliant next step

Structured Google JSON is **not a Google search-results screenshot**. The saved
`page_<n>.json` files are derived provider observation evidence, not a photographic
capture or a complete raw response. UI verification PNGs such as
`structured_google_web.png` depict MY_CUSTOM_BOT, not original Google result pages;
they must never be labeled as Google SERP screenshots.

The removed direct Google path previously received a JavaScript-required shell.
No authentic Google capture has been implemented or verified. Google `--capture`
continues to reject unsupported capture rather than silently opening Bing. A realistic
next workflow is an explicitly approved authentic Google browser/provider screenshot
service: preserve the exact original SERP image, run the existing OCR function, and
attach paths to the correct Google run. If ordinary access is challenged, stop and
report it. A user-permitted manual capture/import with documented URL/query/time and
instructor approval is another possible future workflow; it is not implemented here.
No paid screenshots, new browser navigation or fabricated screenshots were generated
in 05D. Existing capture/OCR tests remain and safe artifact routes are regression-tested.
