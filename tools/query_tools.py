"""
tools/query_tools.py — MCP tools for querying PostgreSQL data.

Tools:
  - execute_query      → run a read-only SELECT query
  - get_table_sample   → fetch sample rows from a table
  - get_table_stats    → row counts, size, vacuum info
  - explain_query      → run EXPLAIN ANALYZE on a SQL statement
"""

import json
import logging
import re
from decimal import Decimal
from datetime import date, datetime, time
from typing import Any, Optional

from database import fetch_all, fetch_one, fetch_val, get_connection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety: block non-SELECT statements in execute_query
# ---------------------------------------------------------------------------

_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|COPY|CALL|DO)\b",
    re.IGNORECASE,
)


def _is_write_statement(sql: str) -> bool:
    return bool(_WRITE_PATTERN.match(sql.strip()))


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_value(v: Any) -> Any:
    """Convert asyncpg-returned types to JSON-safe Python types."""
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return v.hex() if isinstance(v, (bytes, bytearray)) else bytes(v).hex()
    return v


def _serialize_row(row: dict) -> dict:
    return {k: _serialize_value(v) for k, v in row.items()}


def _rows_to_markdown_table(rows: list[dict]) -> str:
    """Format rows as a markdown table."""
    if not rows:
        return "(no rows returned)"
    keys = list(rows[0].keys())
    header = "| " + " | ".join(keys) + " |"
    sep = "| " + " | ".join("---" for _ in keys) + " |"
    body_lines = []
    for row in rows:
        cells = [str(_serialize_value(row.get(k, ""))) for k in keys]
        body_lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + body_lines)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def execute_query(sql: str, limit: int = 100) -> str:
    """
    Execute a read-only SELECT query against the PostgreSQL database.

    This tool only allows SELECT statements. Use execute_write for
    INSERT/UPDATE/DELETE operations.

    Args:
        sql:   A valid PostgreSQL SELECT statement.
        limit: Maximum number of rows to return (default: 100, max: 1000).

    Returns:
        Query results formatted as a markdown table, plus row count.
    """
    sql = sql.strip()

    # Safety check
    if _is_write_statement(sql):
        return (
            "❌ Error: Only SELECT queries are allowed with execute_query.\n"
            "Use the execute_write tool for INSERT/UPDATE/DELETE operations."
        )

    # Enforce row limit
    limit = min(max(1, limit), 1000)

    # Wrap in a subquery to enforce limit if not already present
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        wrapped_sql = f"SELECT * FROM ({sql}) AS _q LIMIT {limit}"
    else:
        wrapped_sql = sql

    try:
        async with get_connection() as conn:
            # Run in a read-only transaction for extra safety
            async with conn.transaction(readonly=True):
                rows = await conn.fetch(wrapped_sql)
                result_rows = [_serialize_row(dict(r)) for r in rows]

        if not result_rows:
            return "✅ Query executed successfully. No rows returned."

        table = _rows_to_markdown_table(result_rows)
        return (
            f"✅ Query returned {len(result_rows)} row(s)"
            + (f" (limited to {limit})" if len(result_rows) == limit else "")
            + f":\n\n{table}"
        )

    except Exception as e:
        logger.error("execute_query error: %s", e)
        return f"❌ Query error: {e}"


async def get_table_sample(
    table: str,
    schema: str = "public",
    limit: int = 10,
) -> str:
    """
    Fetch a sample of rows from a table.

    Args:
        table:  The table name.
        schema: The schema name (default: 'public').
        limit:  Number of rows to return (default: 10, max: 100).

    Returns:
        Sample rows formatted as a markdown table.
    """
    limit = min(max(1, limit), 100)
    # Validate identifiers (prevent injection via table/schema names)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        return f"❌ Invalid table name: '{table}'"
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema):
        return f"❌ Invalid schema name: '{schema}'"

    sql = f'SELECT * FROM "{schema}"."{table}" LIMIT {limit}'
    try:
        async with get_connection() as conn:
            async with conn.transaction(readonly=True):
                rows = await conn.fetch(sql)
                result_rows = [_serialize_row(dict(r)) for r in rows]

        if not result_rows:
            return f"Table '{schema}.{table}' is empty."

        table_md = _rows_to_markdown_table(result_rows)
        return f"📊 Sample from '{schema}.{table}' ({len(result_rows)} rows):\n\n{table_md}"

    except Exception as e:
        logger.error("get_table_sample error: %s", e)
        return f"❌ Error fetching sample: {e}"


async def get_table_stats(table: str, schema: str = "public") -> str:
    """
    Get statistics for a table: row count, size, last vacuum/analyze times.

    Args:
        table:  The table name.
        schema: The schema name (default: 'public').

    Returns:
        Table statistics as formatted text.
    """
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        return f"❌ Invalid table name: '{table}'"
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema):
        return f"❌ Invalid schema name: '{schema}'"

    sql = """
        SELECT
            s.n_live_tup                                        AS live_rows,
            s.n_dead_tup                                        AS dead_rows,
            s.n_mod_since_analyze                               AS rows_since_analyze,
            pg_size_pretty(pg_relation_size($1::regclass))      AS table_size,
            pg_size_pretty(pg_indexes_size($1::regclass))       AS indexes_size,
            pg_size_pretty(pg_total_relation_size($1::regclass)) AS total_size,
            s.last_vacuum,
            s.last_autovacuum,
            s.last_analyze,
            s.last_autoanalyze,
            s.seq_scan,
            s.idx_scan
        FROM pg_stat_user_tables s
        WHERE s.schemaname = $2
          AND s.relname    = $3;
    """
    qualified = f'"{schema}"."{table}"'
    row = await fetch_one(sql, qualified, schema, table)

    if not row:
        # Fallback: just get size
        try:
            size = await fetch_val(
                "SELECT pg_size_pretty(pg_total_relation_size($1::regclass))",
                qualified,
            )
            return f"📊 Stats for '{schema}.{table}':\n  Total size: {size}\n  (No autovacuum stats available — table may be new or unanalyzed)"
        except Exception as e:
            return f"❌ Table '{schema}.{table}' not found: {e}"

    lines = [f"📊 Statistics for '{schema}.{table}':", ""]
    lines.append(f"  Live rows:          {row['live_rows']:,}")
    lines.append(f"  Dead rows:          {row['dead_rows']:,}")
    lines.append(f"  Table size:         {row['table_size']}")
    lines.append(f"  Indexes size:       {row['indexes_size']}")
    lines.append(f"  Total size:         {row['total_size']}")
    lines.append(f"  Sequential scans:   {row['seq_scan']:,}")
    lines.append(f"  Index scans:        {row['idx_scan']:,}")
    lines.append(f"  Last vacuum:        {row['last_vacuum'] or 'never'}")
    lines.append(f"  Last analyze:       {row['last_analyze'] or 'never'}")
    return "\n".join(lines)


async def explain_query(sql: str) -> str:
    """
    Run EXPLAIN ANALYZE on a SQL query to show the execution plan.

    Useful for understanding query performance and index usage.

    Args:
        sql: A valid PostgreSQL SQL statement (SELECT recommended).

    Returns:
        The query execution plan from PostgreSQL.
    """
    sql = sql.strip()
    try:
        async with get_connection() as conn:
            # Use EXPLAIN only (not ANALYZE) to avoid side effects on writes
            explain_sql = f"EXPLAIN (FORMAT TEXT, VERBOSE false) {sql}"
            rows = await conn.fetch(explain_sql)
            plan_lines = [row[0] for row in rows]
            plan = "\n".join(plan_lines)
            return f"📋 Query Plan:\n\n```\n{plan}\n```"
    except Exception as e:
        logger.error("explain_query error: %s", e)
        return f"❌ EXPLAIN error: {e}"
