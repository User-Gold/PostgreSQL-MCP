"""
tools/database_tools.py — MCP tools for database-level information.

Tools:
  - get_database_info  → version, size, connection info
  - list_databases     → list all databases on the server
"""

import logging

from database import fetch_all, fetch_one, fetch_val, get_db_info_summary

logger = logging.getLogger(__name__)


async def get_database_info() -> str:
    """
    Get information about the connected PostgreSQL database:
    version, database size, active connections, and server settings.

    Returns:
        A formatted summary of the database server and current database.
    """
    sql = """
        SELECT
            version()                                           AS pg_version,
            current_database()                                  AS current_db,
            pg_size_pretty(pg_database_size(current_database())) AS db_size,
            (SELECT count(*) FROM pg_stat_activity
             WHERE state = 'active')                            AS active_connections,
            (SELECT count(*) FROM pg_stat_activity)            AS total_connections,
            current_user                                        AS connected_as,
            inet_server_addr()                                  AS server_address,
            inet_server_port()                                  AS server_port,
            pg_postmaster_start_time()                          AS server_started
    """
    row = await fetch_one(sql)
    config = get_db_info_summary()

    lines = ["🐘 PostgreSQL Database Information", "=" * 50]
    if row:
        lines.append(f"  Version:             {row['pg_version']}")
        lines.append(f"  Database:            {row['current_db']}")
        lines.append(f"  Size:                {row['db_size']}")
        lines.append(f"  Connected as:        {row['connected_as']}")
        lines.append(f"  Active connections:  {row['active_connections']}")
        lines.append(f"  Total connections:   {row['total_connections']}")
        lines.append(f"  Server started:      {row['server_started']}")
    lines.append("")
    lines.append("  Connection Config:")
    lines.append(f"    Host:              {config['host']}:{config['port']}")
    lines.append(f"    Pool size:         {config['min_connections']}–{config['max_connections']}")
    lines.append(f"    Write operations:  {'✅ Enabled' if config['write_allowed'] else '🔒 Disabled (read-only)'}")
    return "\n".join(lines)


async def list_databases() -> str:
    """
    List all databases available on the PostgreSQL server.

    Returns:
        Database names, owners, sizes, and encoding.
    """
    sql = """
        SELECT
            d.datname                                       AS database_name,
            pg_catalog.pg_get_userbyid(d.datdba)           AS owner,
            pg_catalog.pg_encoding_to_char(d.encoding)     AS encoding,
            d.datcollate                                    AS collation,
            pg_size_pretty(pg_database_size(d.datname))    AS size,
            CASE WHEN d.datallowconn THEN 'yes' ELSE 'no' END AS connectable
        FROM pg_catalog.pg_database d
        WHERE d.datistemplate = false
        ORDER BY d.datname;
    """
    rows = await fetch_all(sql)
    if not rows:
        return "No databases found."

    lines = ["🗄️  Available Databases:", ""]
    lines.append(f"{'Database':<25} {'Owner':<15} {'Encoding':<10} {'Size':<12} {'Connectable'}")
    lines.append("-" * 75)
    for row in rows:
        lines.append(
            f"{row['database_name']:<25} "
            f"{row['owner']:<15} "
            f"{row['encoding']:<10} "
            f"{row['size']:<12} "
            f"{row['connectable']}"
        )
    return "\n".join(lines)
