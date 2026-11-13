"""Explicit MySQL connectivity checks and search ETL operations."""
import mysql.connector
from mysql.connector import Error, MySQLConnection

from config import get_database_config


def get_connection() -> MySQLConnection:
    """Open a connection; the caller is responsible for closing it."""
    return mysql.connector.connect(**get_database_config(), connection_timeout=5)


def test_connection() -> bool:
    """Return connectivity status without exposing connector error details."""
    try:
        with get_connection() as connection:
            connection.ping(reconnect=False)
        return True
    except (Error, ValueError):
        return False


def get_table_names() -> list[str]:
    """List tables in the configured database, closing all resources."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            return sorted(row[0] for row in cursor.fetchall())


# These helpers share the caller's transaction; run_search commits or rolls back.
def insert_search_query(connection: MySQLConnection, query: str) -> int:
    """Insert the original query and return its ID."""
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO search_queries (query_text) VALUES (%s)", (query,))
        return cursor.lastrowid


def insert_search_run(connection: MySQLConnection, query_id: int, engine: str = "google", provider: str | None = None) -> int:
    """Start an engine-specific run for an existing query."""
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO search_runs (query_id, engine, status, provider) VALUES (%s, %s, %s, %s)",
                       (query_id, engine, "running", provider))
        return cursor.lastrowid


def insert_search_results(connection: MySQLConnection, run_id: int, results: list[dict]) -> None:
    """Store every observation, including invalid URLs, ads and duplicates."""
    if not results:
        return
    with connection.cursor() as cursor:
        for row in results:
            cursor.execute(
                """INSERT INTO search_results
                (run_id, title, original_url, normalized_url, snippet, result_rank, is_ad, is_duplicate, page_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, row["title"], row["original_url"], row["normalized_url"], row["snippet"],
                 row["result_rank"], row["is_ad"], row["is_duplicate"], row.get("page_number")),
            )
            row["id"] = cursor.lastrowid


def update_search_run(connection: MySQLConnection, run_id: int, status: str,
                      counts: dict[str, int], error_message: str | None = None) -> None:
    """Finish a run with the counters for its persisted observations."""
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE search_runs SET status=%s, raw_count=%s, ad_count=%s,
            duplicate_count=%s, final_count=%s, finished_at=CASE WHEN %s='running' THEN NULL ELSE CURRENT_TIMESTAMP END,
            error_message=%s WHERE id=%s""",
            (status, counts["raw_count"], counts["ad_count"], counts["duplicate_count"],
             counts["final_count"], status, error_message, run_id),
        )


def insert_capture_artifact(connection: MySQLConnection, run_id: int,
                            screenshot_path: str, ocr_text_path: str | None) -> int:
    """Attach existing capture files to a run within the caller's transaction."""
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO capture_artifacts (run_id, screenshot_path, ocr_text_path)
            VALUES (%s, %s, %s)""", (run_id, screenshot_path, ocr_text_path),
        )
        return cursor.lastrowid


def get_recent_search_runs() -> list[dict]:
    """Read the latest 20 runs, including their original query text."""
    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("""SELECT r.*, q.query_text FROM search_runs r
                JOIN search_queries q ON q.id=r.query_id ORDER BY r.id DESC LIMIT 20""")
            return cursor.fetchall()


def get_search_run(run_id: int) -> dict | None:
    """Read one run, its raw observations, and capture metadata in one snapshot."""
    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("""SELECT r.*, q.query_text FROM search_runs r
                JOIN search_queries q ON q.id=r.query_id WHERE r.id=%s""", (run_id,))
            run = cursor.fetchone()
            if run is None:
                return None
            cursor.execute("SELECT * FROM search_results WHERE run_id=%s ORDER BY id", (run_id,))
            results = cursor.fetchall()
            cursor.execute("SELECT * FROM capture_artifacts WHERE run_id=%s ORDER BY id", (run_id,))
            return {"run": run, "results": results, "artifacts": cursor.fetchall()}


def get_capture_artifact(artifact_id: int) -> dict | None:
    """Look up artifact paths by database ID, never by a client-provided path."""
    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM capture_artifacts WHERE id=%s", (artifact_id,))
            return cursor.fetchone()


def get_collection_candidates(query: str, engine: str, minimum_count: int) -> list[dict]:
    """Find completed exact-query collections without merging separate runs."""
    with get_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("""SELECT r.* FROM search_runs r
                JOIN search_queries q ON q.id=r.query_id
                WHERE CAST(q.query_text AS BINARY)=CAST(%s AS BINARY)
                AND r.engine=%s AND r.status='completed' AND r.final_count >= %s
                ORDER BY r.final_count DESC, r.id DESC""", (query, engine, minimum_count))
            return cursor.fetchall()


def update_result_duplicates(connection: MySQLConnection, results: list[dict]) -> None:
    """Update flags only on existing observations when a collection is extended."""
    if not results:
        return
    with connection.cursor() as cursor:
        cursor.executemany("UPDATE search_results SET is_duplicate=%s WHERE id=%s",
                           [(row["is_duplicate"], row["id"]) for row in results])


def update_collection_metadata(connection: MySQLConnection, run_id: int, metadata: dict) -> None:
    """Persist non-secret collection state in the same transaction as its results."""
    import json
    with connection.cursor() as cursor:
        cursor.execute("UPDATE search_runs SET collection_metadata=%s WHERE id=%s",
                       (json.dumps(metadata), run_id))
