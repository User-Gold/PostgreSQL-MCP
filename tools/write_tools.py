"""
tools/write_tools.py — MCP tools for write operations (INSERT/UPDATE/DELETE).

Tools:
  - execute_write → run a DML statement (requires ALLOW_WRITE_OPERATIONS=true in .env)

Write operations are disabled by default. Set ALLOW_WRITE_OPERATIONS=true
in your .env file to enable them.
"""

import logging
import re
from typing import Optional

from database import execute, fetch_all, get_connection, is_write_allowed

logger = logging.getLogger(__name__)

# Allowed write statement prefixes
_ALLOWED_WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b",
    re.IGNORECASE,
)

# Dangerous DDL patterns — always blocked
_DANGEROUS_PATTERN = re.compile(
    r"^\s*(DROP|CREATE|ALTER|GRANT|REVOKE|COPY|DO|CALL)\b",
    re.IGNORECASE,
)


async def execute_write(
    sql: str,
    confirm: bool = False,
    return_rows: bool = False,
) -> str:
    """
    Execute a write operation (INSERT, UPDATE, DELETE) on the database.

    ⚠️  Write operations must be explicitly enabled by setting
    ALLOW_WRITE_OPERATIONS=true in your .env file.

    Args:
        sql:         A valid INSERT, UPDATE, or DELETE SQL statement.
        confirm:     Must be set to True to confirm you want to run this.
                     Acts as a safety guard against accidental writes.
        return_rows: If True and the statement has a RETURNING clause,
                     return the affected rows.

    Returns:
        Success message with affected row count, or error details.

    Examples:
        INSERT: "INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com')"
        UPDATE: "UPDATE products SET price = 9.99 WHERE id = 42"
        DELETE: "DELETE FROM sessions WHERE expires_at < NOW()"
    """
    # Check if writes are enabled
    if not is_write_allowed():
        return (
            "❌ Write operations are disabled.\n\n"
            "To enable INSERT/UPDATE/DELETE, set ALLOW_WRITE_OPERATIONS=true "
            "in your .env file and restart the server."
        )

    # Require explicit confirmation
    if not confirm:
        return (
            "⚠️  Write operation not confirmed.\n\n"
            "To execute this write operation, call execute_write with confirm=True.\n"
            f"SQL: {sql[:200]}{'...' if len(sql) > 200 else ''}"
        )

    sql = sql.strip()

    # Block dangerous DDL
    if _DANGEROUS_PATTERN.match(sql):
        return (
            "❌ DDL statements (DROP, CREATE, ALTER, etc.) are not allowed.\n"
            "Only INSERT, UPDATE, DELETE, and TRUNCATE are permitted."
        )

    # Only allow DML
    if not _ALLOWED_WRITE_PATTERN.match(sql):
        return (
            "❌ Only INSERT, UPDATE, DELETE, and TRUNCATE statements are allowed.\n"
            "Use execute_query for SELECT statements."
        )

    try:
        async with get_connection() as conn:
            if return_rows and re.search(r"\bRETURNING\b", sql, re.IGNORECASE):
                rows = await conn.fetch(sql)
                result_rows = [dict(r) for r in rows]
                if result_rows:
                    keys = list(result_rows[0].keys())
                    header = "| " + " | ".join(keys) + " |"
                    sep = "| " + " | ".join("---" for _ in keys) + " |"
                    body = [
                        "| " + " | ".join(str(r.get(k, "")) for k in keys) + " |"
                        for r in result_rows
                    ]
                    table = "\n".join([header, sep] + body)
                    return (
                        f"✅ Write operation successful. "
                        f"{len(result_rows)} row(s) affected:\n\n{table}"
                    )
                return "✅ Write operation successful. No rows returned."
            else:
                status = await conn.execute(sql)
                # status is like "INSERT 0 3" or "UPDATE 5" or "DELETE 2"
                return f"✅ Write operation successful. Status: {status}"

    except Exception as e:
        logger.error("execute_write error: %s", e)
        return f"❌ Write error: {e}"
