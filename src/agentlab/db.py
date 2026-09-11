"""A bounded pool whose login has SELECT privileges only, even outside transactions."""

from __future__ import annotations

import atexit
import os
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    pool = ConnectionPool(
        kwargs={
            "host": "127.0.0.1",
            "port": int(os.getenv("AGENTLAB_DB_PORT", "55432")),
            "dbname": "agentlab",
            "user": "agentlab_readonly",
            "password": "agentlab",
            "connect_timeout": 3,
            "options": "-c default_transaction_read_only=on -c statement_timeout=2000 "
            "-c lock_timeout=500 -c search_path=public,pg_catalog",
            "row_factory": dict_row,
        },
        min_size=1,
        max_size=4,
        timeout=5,
        open=True,
    )
    atexit.register(pool.close)
    return pool


def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    """Internal SQL helper; exposed tools must aggregate and impose their own bounds."""
    with get_pool().connection() as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            return connection.execute(sql, params).fetchall()
