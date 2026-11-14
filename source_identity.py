"""Reuse exact validated source URLs while preserving per-run observations."""
from hashlib import sha256


def source_id(connection, url: str | None) -> int | None:
    if not url:
        return None
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO source_catalog (url_hash,url) VALUES (%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)',
                       (sha256(url.encode('utf-8')).digest(),url))
        return cursor.lastrowid


def backfill_sources() -> int:
    """Attach historical observations after the additive SQL migration; delete none."""
    import db
    assigned=0
    with db.get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id,normalized_url FROM search_results WHERE source_id IS NULL AND normalized_url IS NOT NULL')
                for observation_id,url in cursor.fetchall():
                    identity=source_id(connection,url)
                    cursor.execute('UPDATE search_results SET source_id=%s WHERE id=%s',(identity,observation_id))
                    assigned+=1
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return assigned
