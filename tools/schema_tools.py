"""
tools/schema_tools.py — MCP tools for exploring the PostgreSQL schema.

Tools:
  - list_schemas        → list all schemas in the connected database
  - list_tables         → list tables in a given schema
  - describe_table      → full column/constraint info for a table
  - search_schema       → search tables and columns by keyword
  - list_indexes        → list indexes on a table
"""

import json
import logging
from typing import Any

from database import fetch_all, fetch_one

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """Make asyncpg types JSON-serializable."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    # Handle Decimal, datetime, etc.
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _rows_to_text(rows: list[dict], title: str = "") -> str:
    """Format a list of dicts as a readable text table."""
    if not rows:
        return f"{title}\n(no results)" if title else "(no results)"
    keys = list(rows[0].keys())
    col_widths = {k: max(len(k), max(len(str(r.get(k, ""))) for r in rows)) for k in keys}
    header = " | ".join(k.ljust(col_widths[k]) for k in keys)
    sep = "-+-".join("-" * col_widths[k] for k in keys)
    lines = [title, header, sep] if title else [header, sep]
    for row in rows:
        lines.append(" | ".join(str(row.get(k, "")).ljust(col_widths[k]) for k in keys))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

async def list_schemas() -> str:
    """
    List all schemas in the connected PostgreSQL database.
    Returns schema names, owner, and whether they contain tables.
    """
    sql = """
        SELECT
            n.nspname                                   AS schema_name,
            pg_catalog.pg_get_userbyid(n.nspowner)     AS owner,
            COUNT(c.relname)                            AS table_count
        FROM pg_catalog.pg_namespace n
        LEFT JOIN pg_catalog.pg_class c
            ON c.relnamespace = n.oid AND c.relkind = 'r'
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND n.nspname NOT LIKE 'pg_temp_%'
          AND n.nspname NOT LIKE 'pg_toast_temp_%'
        GROUP BY n.nspname, n.nspowner
        ORDER BY n.nspname;
    """
    rows = await fetch_all(sql)
    if not rows:
        return "No user-defined schemas found in this database."
    return _rows_to_text(rows, "📂 Schemas in database:")


async def list_tables(schema: str = "public") -> str:
    """
    List all tables in the specified schema.

    Args:
        schema: The schema name to list tables from (default: 'public').

    Returns:
        A formatted list of tables with row estimates and sizes.
    """
    sql = """
        SELECT
            t.table_name,
            t.table_type,
            pg_size_pretty(pg_total_relation_size(
                quote_ident(t.table_schema) || '.' || quote_ident(t.table_name)
            ))                                          AS total_size,
            COALESCE(s.n_live_tup, 0)                  AS estimated_rows,
            t.table_schema                              AS schema_name
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s
            ON s.schemaname = t.table_schema
           AND s.relname    = t.table_name
        WHERE t.table_schema = $1
          AND t.table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY t.table_name;
    """
    rows = await fetch_all(sql, schema)
    if not rows:
        return f"No tables found in schema '{schema}'."
    return _rows_to_text(rows, f"📋 Tables in schema '{schema}':")


async def describe_table(table: str, schema: str = "public") -> str:
    """
    Describe a table: columns, data types, nullability, defaults,
    primary keys, and foreign keys.

    Args:
        table:  The table name.
        schema: The schema name (default: 'public').

    Returns:
        A detailed description of the table structure.
    """
    # Column info
    col_sql = """
        SELECT
            c.column_name,
            c.data_type,
            c.character_maximum_length,
            c.is_nullable,
            c.column_default,
            c.ordinal_position
        FROM information_schema.columns c
        WHERE c.table_schema = $1
          AND c.table_name   = $2
        ORDER BY c.ordinal_position;
    """
    columns = await fetch_all(col_sql, schema, table)
    if not columns:
        return f"Table '{schema}.{table}' not found or has no columns."

    # Primary keys
    pk_sql = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema    = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema    = $1
          AND tc.table_name      = $2;
    """
    pk_rows = await fetch_all(pk_sql, schema, table)
    pk_cols = {r["column_name"] for r in pk_rows}

    # Foreign keys
    fk_sql = """
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_schema,
            ccu.table_name   AS foreign_table,
            ccu.column_name  AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema    = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = $1
          AND tc.table_name      = $2;
    """
    fk_rows = await fetch_all(fk_sql, schema, table)
    fk_map = {r["column_name"]: r for r in fk_rows}

    # Build output
    lines = [f"🗂️  Table: {schema}.{table}", "=" * 60]
    lines.append(f"{'Column':<25} {'Type':<20} {'Nullable':<10} {'PK':<5} {'FK / Default'}")
    lines.append("-" * 80)

    for col in columns:
        name = col["column_name"]
        dtype = col["data_type"]
        if col["character_maximum_length"]:
            dtype += f"({col['character_maximum_length']})"
        nullable = col["is_nullable"]
        pk_flag = "✓" if name in pk_cols else ""
        extra = ""
        if name in fk_map:
            fk = fk_map[name]
            extra = f"→ {fk['foreign_schema']}.{fk['foreign_table']}.{fk['foreign_column']}"
        elif col["column_default"]:
            extra = f"default: {col['column_default']}"
        lines.append(f"{name:<25} {dtype:<20} {nullable:<10} {pk_flag:<5} {extra}")

    if pk_cols:
        lines.append(f"\n🔑 Primary Key: {', '.join(sorted(pk_cols))}")
    if fk_rows:
        lines.append("\n🔗 Foreign Keys:")
        for fk in fk_rows:
            lines.append(
                f"   {fk['column_name']} → "
                f"{fk['foreign_schema']}.{fk['foreign_table']}.{fk['foreign_column']}"
            )

    return "\n".join(lines)


async def search_schema(keyword: str) -> str:
    """
    Search for tables and columns whose names contain the given keyword.

    Args:
        keyword: The search term (case-insensitive).

    Returns:
        Matching tables and columns across all user schemas.
    """
    sql = """
        SELECT
            c.table_schema,
            c.table_name,
            c.column_name,
            c.data_type,
            CASE
                WHEN c.table_name ILIKE $1 THEN 'table match'
                ELSE 'column match'
            END AS match_type
        FROM information_schema.columns c
        WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (c.table_name ILIKE $1 OR c.column_name ILIKE $1)
        ORDER BY c.table_schema, c.table_name, c.column_name
        LIMIT 100;
    """
    pattern = f"%{keyword}%"
    rows = await fetch_all(sql, pattern)
    if not rows:
        return f"No tables or columns matching '{keyword}' found."
    return _rows_to_text(rows, f"🔍 Search results for '{keyword}':")


async def list_indexes(table: str, schema: str = "public") -> str:
    """
    List all indexes on a table.

    Args:
        table:  The table name.
        schema: The schema name (default: 'public').

    Returns:
        Index names, columns, and type.
    """
    sql = """
        SELECT
            i.relname                                   AS index_name,
            am.amname                                   AS index_type,
            ix.indisunique                              AS is_unique,
            ix.indisprimary                             AS is_primary,
            array_to_string(
                ARRAY(
                    SELECT pg_get_indexdef(ix.indexrelid, k + 1, true)
                    FROM generate_subscripts(ix.indkey, 1) AS k
                    ORDER BY k
                ), ', '
            )                                           AS columns
        FROM pg_class t
        JOIN pg_index ix    ON t.oid = ix.indrelid
        JOIN pg_class i     ON i.oid = ix.indexrelid
        JOIN pg_am am       ON i.relam = am.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE t.relname  = $1
          AND n.nspname  = $2
        ORDER BY i.relname;
    """
    rows = await fetch_all(sql, table, schema)
    if not rows:
        return f"No indexes found on '{schema}.{table}'."
    return _rows_to_text(rows, f"📇 Indexes on '{schema}.{table}':")
