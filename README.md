# MY_CUSTOM_BOT

CCNY DSE I2400 Advanced Web Scraping project. Milestone 01 provides configuration,
a MySQL schema, and three JSON endpoints. The existing assignment document and
`WebSearch_Google_Python_Script.py` are preserved as reference material.

## Files and responsibilities

```text
AGENTS.md
main.py
config.py
db.py
requirements.txt
.env.example
.gitignore
README.md
sql/schema.sql
tests/test_config.py
tests/test_app.py
```

- `config.py` reads `.env` beside the module using python-dotenv. Process environment
  values take precedence. It checks required settings and the port range. An explicit
  empty password is allowed for local setups; a missing password setting is rejected.
- `db.py` uses mysql-connector-python for direct SQL access. `get_connection()` returns
  a connection owned by the caller. `test_connection()` returns a boolean;
  `get_table_names()` executes `SHOW TABLES`. Both checks close their connections.
  There are no writes yet. Future writes must commit on success and roll back on failure.
- `main.py` uses FastAPI to serve `/`, `/health`, and `/db-health`. The database
  endpoint executes a table query to verify access and returns HTTP 503 for configuration
  or connector failures, without returning the underlying error or credentials.
- `sql/schema.sql` is the schema to execute manually in Workbench.
- `tests/` uses pytest and FastAPI's TestClient (which needs httpx) to check configuration
  and routes. Database calls are mocked, so these tests require no MySQL credentials.
- Uvicorn runs the application. No frontend or search functionality is implemented.

## Setup and verification

Prerequisites: Python 3.10 or newer, MySQL 8 (8.0.16+ for enforced CHECK constraints),
MySQL Workbench, and access to an existing MySQL account allowed to create the database
and tables. This milestone does not change accounts or privileges.

From a terminal:

```sh
cd "/Users/dmitrii/Documents/CCNY 2026/Data Engineering/Web Scraping Project"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Run the copy command only if `.env` does not already exist. Edit `.env` locally to
provide your MySQL settings. Never commit it or print its contents. The application
never creates or overwrites this file and never creates the database automatically.

In MySQL Workbench:

1. Open your local MySQL connection with your existing credentials.
2. Choose **File → Open SQL Script**, then open `sql/schema.sql` in this project.
3. Review the script and run the entire script using the execute-all lightning button.
4. Refresh the Schemas panel, expand `MY_CUSTOM_BOT`, then expand Tables.
5. Open a new SQL tab and execute the verification queries below.

```sql
USE MY_CUSTOM_BOT;
SHOW TABLES;
DESCRIBE search_queries;
DESCRIBE search_runs;
DESCRIBE search_results;
DESCRIBE capture_artifacts;
DESCRIBE ai_responses;
DESCRIBE ai_summaries;
SELECT * FROM search_queries;
SELECT * FROM search_runs;
SELECT * FROM search_results;
```

There should be six tables; the new tables contain no rows. No sample data is inserted.
The script uses `IF NOT EXISTS`, so rerunning it preserves existing data. It does not
migrate or validate definitions of tables that already exist; inspect those manually.
MySQL DDL can commit implicitly, so the script is not an atomic migration.

Start and test the application:

```sh
python -m pytest -q
python -m uvicorn main:app --reload
```

In a second terminal:

```sh
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/db-health
```

The first two routes work without a configured database. `/db-health` returns status
`ok` and table names after setup; an empty list means the database is reachable but
has no tables. A 503 means you should check `.env`, the MySQL service, and database
access in Workbench. This route checks access, not schema completeness.

To run the standalone connectivity checks after configuring `.env`:

```sh
python -c "from db import test_connection; print(test_connection())"
python -c "from db import get_table_names; print(get_table_names())"
```

## Tables and relationships

| Table | Purpose and relationship |
| --- | --- |
| search_queries | User search text; parent of runs, AI responses, and summaries. |
| search_runs | Execution engine, status, counts, timing, and errors; belongs to one query. |
| search_results | Raw URLs and extraction metadata; belongs to one run. Ad and duplicate flags preserve audit observations. |
| capture_artifacts | Screenshot/OCR file paths; belongs to one run. File contents stay on disk. |
| ai_responses | Provider/model output; belongs to one query. |
| ai_summaries | Summarized output and summarizer; belongs to one query. |

InnoDB enforces foreign keys. All foreign keys have explicit lookup indexes and
RESTRICT deletion/update behavior to protect dependent records. utf8mb4 supports
full Unicode; the chosen collation requires MySQL 8. BOOLEAN is MySQL's TINYINT(1)
alias. Counts cannot be negative. IDs use BIGINT and AUTO_INCREMENT. URLs have no
unique constraint so duplicate observations remain available for later ETL auditing.
Query word-count validation and status conventions will be defined in later milestones.

## Limits and future work

The schema must be run manually; automated tests do not verify it against a live
MySQL server. Dependencies have compatible version ranges rather than a lock file.
This milestone has no search providers, ETL, ad filtering, URL normalization, screenshot
capture, OCR, AI calls, summarization, HTML GUI, or 50-result display. Those belong to
future milestones. No data, database accounts, or system settings are modified by the app.
