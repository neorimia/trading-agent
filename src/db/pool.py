"""Process-local Psycopg connection pools."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.db.config import DatabaseSettings

_LOCK = threading.Lock()
_POOLS: dict[str, ConnectionPool] = {}


def get_database_pool(
    url: str,
    *,
    min_size: int = 1,
    max_size: int = 5,
    timeout_s: float = 5.0,
) -> ConnectionPool:
    settings = DatabaseSettings(
        url=url,
        min_pool_size=min_size,
        max_pool_size=max_size,
        timeout_s=timeout_s,
    )
    with _LOCK:
        pool = _POOLS.get(settings.url)
        if pool is None:
            pool = ConnectionPool(
                conninfo=settings.url,
                min_size=settings.min_pool_size,
                max_size=settings.max_pool_size,
                timeout=settings.timeout_s,
                kwargs={"row_factory": dict_row},
                open=True,
            )
            _POOLS[settings.url] = pool
        return pool


@contextmanager
def database_connection(url: str) -> Iterator[Connection]:
    with get_database_pool(url).connection() as connection:
        yield connection


def database_ready(url: str) -> bool:
    try:
        with database_connection(url) as connection:
            row = connection.execute("SELECT 1 AS ready").fetchone()
            return bool(row and row["ready"] == 1)
    except Exception:
        return False


def close_database_pools() -> None:
    with _LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()
