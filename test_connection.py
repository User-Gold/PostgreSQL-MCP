r"""
test_connection.py — Verify your PostgreSQL connection before starting the MCP server.

Usage:
    python test_connection.py
    (or)
    .venv\Scripts\python.exe test_connection.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ── Read credentials from .env ──────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME", "postgres")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# ── Colors for terminal output ───────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


async def test_connection():
    try:
        import asyncpg
    except ImportError:
        print(f"{RED}✗ asyncpg not installed.{RESET}")
        print(f"  Run: pip install asyncpg  (or .venv\\Scripts\\pip install asyncpg)")
        sys.exit(1)

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  PostgreSQL MCP Server — Connection Test{RESET}")
    print(f"{BOLD}{'='*55}{RESET}\n")

    print(f"{CYAN}  Config loaded from .env:{RESET}")
    print(f"    Host     : {DB_HOST}")
    print(f"    Port     : {DB_PORT}")
    print(f"    Database : {DB_NAME}")
    print(f"    User     : {DB_USER}")
    print(f"    Password : {'*' * len(DB_PASSWORD) if DB_PASSWORD else '(empty)'}")
    print()

    # ── 1. Test basic connection ─────────────────────────────────────────────
    print(f"  {YELLOW}[1/4]{RESET} Connecting to PostgreSQL...", end=" ", flush=True)
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10,
        )
        print(f"{GREEN}✓ Connected{RESET}")
    except Exception as e:
        print(f"{RED}✗ FAILED{RESET}")
        print(f"\n  {RED}Error: {e}{RESET}")
        print(f"\n  {YELLOW}Tips:{RESET}")
        print(f"    • Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env")
        print(f"    • Is PostgreSQL running?  Try: pg_isready -h {DB_HOST} -p {DB_PORT}")
        print(f"    • Test manually:  psql -h {DB_HOST} -p {DB_PORT} -U {DB_USER} -d {DB_NAME}")
        sys.exit(1)

    # ── 2. Server version ────────────────────────────────────────────────────
    print(f"  {YELLOW}[2/4]{RESET} Checking server version...", end=" ", flush=True)
    try:
        version = await conn.fetchval("SELECT version()")
        short_version = version.split(",")[0]  # e.g. "PostgreSQL 16.1 on x86_64..."
        print(f"{GREEN}✓{RESET} {short_version}")
    except Exception as e:
        print(f"{RED}✗ {e}{RESET}")

    # ── 3. List schemas ──────────────────────────────────────────────────────
    print(f"  {YELLOW}[3/4]{RESET} Listing schemas...", end=" ", flush=True)
    try:
        schemas = await conn.fetch("""
            SELECT nspname AS schema_name
            FROM pg_catalog.pg_namespace
            WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast')
              AND nspname NOT LIKE 'pg_temp_%'
            ORDER BY nspname
        """)
        schema_names = [r["schema_name"] for r in schemas]
        print(f"{GREEN}✓{RESET} Found {len(schema_names)} schema(s): {', '.join(schema_names) or '(none)'}")
    except Exception as e:
        print(f"{RED}✗ {e}{RESET}")

    # ── 4. List tables ───────────────────────────────────────────────────────
    print(f"  {YELLOW}[4/4]{RESET} Listing tables in 'public' schema...", end=" ", flush=True)
    try:
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        table_names = [r["table_name"] for r in tables]
        if table_names:
            print(f"{GREEN}✓{RESET} Found {len(table_names)} table(s):")
            for t in table_names:
                print(f"       • {t}")
        else:
            print(f"{GREEN}✓{RESET} No tables in 'public' schema yet")
    except Exception as e:
        print(f"{RED}✗ {e}{RESET}")

    await conn.close()

    print(f"\n{GREEN}{BOLD}  ✅ All checks passed! Your database is ready.{RESET}")
    print(f"  You can now start the MCP server with:  python main.py\n")


if __name__ == "__main__":
    asyncio.run(test_connection())
