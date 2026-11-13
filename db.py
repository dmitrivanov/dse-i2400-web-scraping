"""Small, read-only MySQL connectivity checks."""
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
