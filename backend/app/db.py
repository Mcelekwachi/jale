"""Database access. Raw SQL over psycopg3 with an async pool — no ORM.

The schema is the source of truth and the queries are small enough to read,
which keeps the mapping between schema.sql and the API obvious.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

_pool: AsyncConnectionPool | None = None


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.pool_min_size,
            max_size=settings.pool_max_size,
            open=False,
            kwargs={"row_factory": dict_row},
        )
        await _pool.open(wait=True, timeout=15)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("connection pool is not open")
    return _pool


async def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute(sql, params or {})
        return await cur.fetchall()


async def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict | None:
    async with get_pool().connection() as conn:
        cur = await conn.execute(sql, params or {})
        return await cur.fetchone()
