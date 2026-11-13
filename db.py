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


def insert_search_run(connection: MySQLConnection, query_id: int, engine: str = "google") -> int:
    """Start an engine-specific run for an existing query."""
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO search_runs (query_id, engine, status) VALUES (%s, %s, %s)",
                       (query_id, engine, "running"))
        return cursor.lastrowid


def insert_search_results(connection: MySQLConnection, run_id: int, results: list[dict]) -> None:
    """Store every observation, including invalid URLs, ads and duplicates."""
    if not results:
        return
    with connection.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO search_results
            (run_id, title, original_url, normalized_url, snippet, result_rank, is_ad, is_duplicate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            [(run_id, row["title"], row["original_url"], row["normalized_url"], row["snippet"],
              row["result_rank"], row["is_ad"], row["is_duplicate"]) for row in results],
        )


def update_search_run(connection: MySQLConnection, run_id: int, status: str,
                      counts: dict[str, int], error_message: str | None = None) -> None:
    """Finish a run with the counters for its persisted observations."""
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE search_runs SET status=%s, raw_count=%s, ad_count=%s,
            duplicate_count=%s, final_count=%s, finished_at=CURRENT_TIMESTAMP,
            error_message=%s WHERE id=%s""",
            (status, counts["raw_count"], counts["ad_count"], counts["duplicate_count"],
             counts["final_count"], error_message, run_id),
        )
