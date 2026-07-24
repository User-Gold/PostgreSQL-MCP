"""
main.py — PostgreSQL MCP Server for Claude Desktop

This is the main entry point. It creates a FastMCP server and registers:
  - 12 Tools    (schema exploration, querying, write operations, DB info)
  - 2 Resources (schema overview, table data)
  - 2 Prompts   (analyze_table, write_sql_query)

Credentials are loaded automatically from the .env file in the project root.

Usage:
  python main.py

Claude Desktop config (add to claude_desktop_config.json):
  {
    "mcpServers": {
      "postgres": {
        "command": "[PATH_TO_YOUR_VENV_PYTHON_EXE]",
        "args": ["main.py"],
        "cwd": "[PATH_TO_YOUR_PROJECT_ROOT]",
        "env": {
          "PYTHONPATH": "[PATH_TO_YOUR_PROJECT_ROOT]"
        }
      }
    }
  }
"""


import asyncio
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env before anything else
load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,  # MCP uses stdout for protocol; logs go to stderr
)
logger = logging.getLogger("mcp_postgres")

# ---------------------------------------------------------------------------
# Import tool implementations
# ---------------------------------------------------------------------------

from database import close_pool, get_pool, get_db_info_summary, fetch_all, get_connection
from tools.schema_tools import (
    list_schemas,
    list_tables,
    describe_table,
    search_schema,
    list_indexes,
)
from tools.query_tools import (
    execute_query,
    get_table_sample,
    get_table_stats,
    explain_query,
)
from tools.write_tools import execute_write
from tools.database_tools import get_database_info, list_databases

# ---------------------------------------------------------------------------
# Lifespan: initialize and teardown the DB pool
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Initialize DB pool on startup, close it on shutdown."""
    logger.info("🚀 Starting PostgreSQL MCP Server...")
    config = get_db_info_summary()
    logger.info(
        "Connecting to %s:%s/%s as %s",
        config["host"], config["port"], config["database"], config["user"],
    )
    try:
        await get_pool()
        logger.info("✅ Database connection pool ready.")
    except Exception as e:
        logger.error("❌ Failed to connect to database: %s", e)
        logger.error(
            "Check your .env file — DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"
        )
        raise

    yield  # Server is running

    logger.info("🛑 Shutting down — closing DB pool...")
    await close_pool()
    logger.info("Goodbye.")


# ---------------------------------------------------------------------------
# Create the MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="PostgreSQL MCP Server",
    instructions=(
        "You are connected to a PostgreSQL database. "
        "Use the available tools to explore the schema, query data, and (if enabled) "
        "perform write operations. Always use describe_table before writing queries "
        "to understand the table structure. Use execute_query for SELECT statements "
        "and execute_write (with confirm=True) for INSERT/UPDATE/DELETE."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Register Tools
# ---------------------------------------------------------------------------

# --- Database-level ---
mcp.tool()(get_database_info)
mcp.tool()(list_databases)

# --- Schema exploration ---
mcp.tool()(list_schemas)
mcp.tool()(list_tables)
mcp.tool()(describe_table)
mcp.tool()(search_schema)
mcp.tool()(list_indexes)

# --- Querying ---
mcp.tool()(execute_query)
mcp.tool()(get_table_sample)
mcp.tool()(get_table_stats)
mcp.tool()(explain_query)

# --- Write operations ---
mcp.tool()(execute_write)

# ---------------------------------------------------------------------------
# Register Resources
# ---------------------------------------------------------------------------

@mcp.resource("schema://overview")
async def schema_overview() -> str:
    """
    Full schema overview of the connected database.
    Lists all user schemas, their tables, and column summaries.
    Use this to get a bird's-eye view of the database structure.
    """
    sql = """
        SELECT
            c.table_schema,
            c.table_name,
            string_agg(
                c.column_name || ' ' || c.data_type,
                ', ' ORDER BY c.ordinal_position
            ) AS columns
        FROM information_schema.columns c
        WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
        GROUP BY c.table_schema, c.table_name
        ORDER BY c.table_schema, c.table_name;
    """
    rows = await fetch_all(sql)
    if not rows:
        return "No user tables found in this database."

    lines = ["# Database Schema Overview", ""]
    current_schema = None
    for row in rows:
        if row["table_schema"] != current_schema:
            current_schema = row["table_schema"]
            lines.append(f"\n## Schema: {current_schema}")
        lines.append(f"\n### {row['table_name']}")
        lines.append(f"Columns: {row['columns']}")

    return "\n".join(lines)


@mcp.resource("table://{schema}/{table}")
async def table_resource(schema: str, table: str) -> str:
    """
    Detailed information and sample data for a specific table.
    URI format: table://{schema}/{table}
    Example:    table://public/users
    """
    # Validate identifiers
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        return f"Invalid table name: '{table}'"
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema):
        return f"Invalid schema name: '{schema}'"

    # Get column info
    col_sql = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position;
    """
    columns = await fetch_all(col_sql, schema, table)
    if not columns:
        return f"Table '{schema}.{table}' not found."

    lines = [f"# Table: {schema}.{table}", "", "## Columns", ""]
    lines.append(f"{'Column':<25} {'Type':<20} {'Nullable':<10} Default")
    lines.append("-" * 70)
    for col in columns:
        lines.append(
            f"{col['column_name']:<25} "
            f"{col['data_type']:<20} "
            f"{col['is_nullable']:<10} "
            f"{col['column_default'] or ''}"
        )

    # Sample data
    try:
        async with get_connection() as conn:
            async with conn.transaction(readonly=True):
                rows = await conn.fetch(f'SELECT * FROM "{schema}"."{table}" LIMIT 5')
                sample = [dict(r) for r in rows]

        if sample:
            lines.append("\n## Sample Data (5 rows)\n")
            keys = list(sample[0].keys())
            lines.append("| " + " | ".join(keys) + " |")
            lines.append("| " + " | ".join("---" for _ in keys) + " |")
            for row in sample:
                cells = [str(row.get(k, "")) for k in keys]
                lines.append("| " + " | ".join(cells) + " |")
        else:
            lines.append("\n## Sample Data\n(table is empty)")
    except Exception as e:
        lines.append(f"\n## Sample Data\n(error fetching sample: {e})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Register Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
def analyze_table(schema: str = "public", table: str = "") -> str:
    """
    Generate a prompt to analyze a database table.

    Args:
        schema: The schema name (default: 'public').
        table:  The table name to analyze.
    """
    if not table:
        return (
            "Please provide a table name to analyze. "
            "First use list_tables to see available tables."
        )
    return (
        f"Please analyze the table '{schema}.{table}' in my PostgreSQL database.\n\n"
        f"Steps:\n"
        f"1. Use describe_table(table='{table}', schema='{schema}') to understand the structure\n"
        f"2. Use get_table_stats(table='{table}', schema='{schema}') to see size and row counts\n"
        f"3. Use get_table_sample(table='{table}', schema='{schema}') to see example data\n"
        f"4. Provide insights about:\n"
        f"   - What this table likely stores and its purpose\n"
        f"   - Data quality observations (nulls, defaults)\n"
        f"   - Relationships to other tables (foreign keys)\n"
        f"   - Suggested queries for common use cases\n"
    )


@mcp.prompt()
def write_sql_query(
    description: str = "",
    schema: str = "public",
    tables: str = "",
) -> str:
    """
    Generate a prompt to write a SQL query from a natural language description.

    Args:
        description: What you want the query to do (in plain English).
        schema:      The schema to query (default: 'public').
        tables:      Comma-separated list of relevant table names (optional).
    """
    table_hint = ""
    if tables:
        table_list = [t.strip() for t in tables.split(",")]
        table_hint = (
            f"\n\nRelevant tables: {', '.join(table_list)}\n"
            f"Please use describe_table for each table before writing the query."
        )

    return (
        f"Please write a PostgreSQL SQL query that does the following:\n\n"
        f"{description or '(describe what you want the query to do)'}\n"
        f"{table_hint}\n\n"
        f"Schema: {schema}\n\n"
        f"Requirements:\n"
        f"- Write a valid PostgreSQL query\n"
        f"- Use proper JOINs if multiple tables are needed\n"
        f"- Add comments explaining complex parts\n"
        f"- Consider performance (use indexes where possible)\n"
        f"- After writing the query, use execute_query to run it and show the results\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting MCP server with stdio transport...")
    mcp.run(transport="stdio")
