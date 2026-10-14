"""
database.py — Async PostgreSQL connection pool manager.

Reads credentials from .env and provides a shared asyncpg pool
that all MCP tools use.
"""

import asyncpg
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "min_size": int(os.getenv("DB_MIN_CONNECTIONS", "1")),
    "max_size": int(os.getenv("DB_MAX_CONNECTIONS", "10")),
}

ALLOW_WRITE = os.getenv("ALLOW_WRITE_OPERATIONS", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Pool singleton
# ---------------------------------------------------------------------------

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it if needed."""
    global _pool
    if _pool is None:
        logger.info(
            "Creating connection pool → %s:%s/%s",
            DB_CONFIG["host"],
            DB_CONFIG["port"],
            DB_CONFIG["database"],
        )
        _pool = await asyncpg.create_pool(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"] or None,
            min_size=DB_CONFIG["min_size"],
            max_size=DB_CONFIG["max_size"],
            command_timeout=60,
        )
        logger.info("Connection pool ready.")
    return _pool


async def close_pool() -> None:
    """Gracefully close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Connection pool closed.")


@asynccontextmanager
async def get_connection():
    """Async context manager that yields a single connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def fetch_all(sql: str, *args) -> list[dict]:
    """Execute a query and return all rows as a list of dicts."""
    async with get_connection() as conn:
        rows = await conn.fetch(sql, *args)
        return [dict(row) for row in rows]


async def fetch_one(sql: str, *args) -> Optional[dict]:
    """Execute a query and return the first row as a dict (or None)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(sql, *args)
        return dict(row) if row else None


async def fetch_val(sql: str, *args):
    """Execute a query and return a single scalar value."""
    async with get_connection() as conn:
        return await conn.fetchval(sql, *args)


async def execute(sql: str, *args) -> str:
    """Execute a DML statement and return the status string."""
    async with get_connection() as conn:
        return await conn.execute(sql, *args)


def is_write_allowed() -> bool:
    """Return True if write operations are enabled via .env."""
    return ALLOW_WRITE


def get_db_info_summary() -> dict:
    """Return a summary of the current DB config (no password)."""
    return {
        "host": DB_CONFIG["host"],
        "port": DB_CONFIG["port"],
        "database": DB_CONFIG["database"],
        "user": DB_CONFIG["user"],
        "min_connections": DB_CONFIG["min_size"],
        "max_connections": DB_CONFIG["max_size"],
        "write_allowed": ALLOW_WRITE,
    }
