# 🐘 PostgreSQL MCP Server for Claude Desktop

Connect **Claude Desktop** to your PostgreSQL database using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). Ask Claude questions in plain English and it will query your database, explore schemas, and analyze data — no SQL required.

---

## ✨ Features

| Category | Tools |
|---|---|
| 🗄️ Database Info | `get_database_info`, `list_databases` |
| 📂 Schema Exploration | `list_schemas`, `list_tables`, `describe_table`, `search_schema`, `list_indexes` |
| 🔍 Querying | `execute_query`, `get_table_sample`, `get_table_stats`, `explain_query` |
| ✏️ Write Operations | `execute_write` (disabled by default — opt-in via `.env`) |
| 📄 Resources | `schema://overview`, `table://{schema}/{table}` |
| 💬 Prompts | `analyze_table`, `write_sql_query` |

---

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/User-Gold/PostgreSQL-MCP.git
cd PostgreSQL-MCP
```

### 2. Create a Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Your Database

```bash
# Copy the example env file
cp .env.example .env
```

Edit `.env` with your PostgreSQL credentials:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database_name
DB_USER=your_username
DB_PASSWORD=your_password

# Set to "true" to allow INSERT/UPDATE/DELETE
ALLOW_WRITE_OPERATIONS=false
```

> **All credentials live only in `.env`** — they are never put in the Claude Desktop config file.

### 5. Test the Server

```bash
python main.py
```

You should see:
```
🚀 Starting PostgreSQL MCP Server...
✅ Database connection pool ready.
```

Press `Ctrl+C` to stop.

### 6. Connect to Claude Desktop

**Find your Claude Desktop config file:**

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

**Add the `postgres` block** to the `mcpServers` section (update the path):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "[PATH_TO_YOUR_VENV_PYTHON_EXE]",
      "args": ["[PATH_TO_YOUR_PROJECT_ROOT]\\main.py"],
      "cwd": "[PATH_TO_YOUR_PROJECT_ROOT]",
      "env": {
        "PYTHONPATH": "[PATH_TO_YOUR_PROJECT_ROOT]"
      }
    }
  }
}
```

> **Note:** No DB credentials go in this file. The server reads them automatically from your `.env` file using `python-dotenv`.

**Restart Claude Desktop** after saving the config.

---

## 💬 Example Conversations with Claude

Once connected, try asking Claude:

```
"List all tables in my database"
"Describe the structure of the users table"
"Show me 10 sample rows from the orders table"
"How many rows are in each table in the public schema?"
"Find all columns related to 'email' across all tables"
"What indexes exist on the products table?"
"Write a query to find the top 10 customers by total order value"
"Explain why this query might be slow: SELECT * FROM orders WHERE status = 'pending'"
```

---

## 🔧 Tool Reference

### Database Info
| Tool | Description |
|---|---|
| `get_database_info` | PostgreSQL version, DB size, connection count, server info |
| `list_databases` | All databases on the server with sizes and encoding |

### Schema Exploration
| Tool | Description |
|---|---|
| `list_schemas()` | All user-defined schemas in the connected database |
| `list_tables(schema)` | Tables in a schema with row counts and sizes |
| `describe_table(table, schema)` | Columns, types, nullable, defaults, PKs, FKs |
| `search_schema(keyword)` | Find tables/columns by keyword (case-insensitive) |
| `list_indexes(table, schema)` | Indexes on a table with type and columns |

### Querying
| Tool | Description |
|---|---|
| `execute_query(sql, limit)` | Read-only SELECT (enforced via read-only transaction) |
| `get_table_sample(table, schema, limit)` | Sample rows from a table (max 100) |
| `get_table_stats(table, schema)` | Row counts, sizes, vacuum/analyze timestamps |
| `explain_query(sql)` | EXPLAIN execution plan (no data modification) |

### Write Operations
| Tool | Description |
|---|---|
| `execute_write(sql, confirm)` | INSERT/UPDATE/DELETE — requires `ALLOW_WRITE_OPERATIONS=true` in `.env` AND `confirm=True` |

---

## 🔒 Security

- **Read-only by default** — write operations require explicit opt-in in `.env`
- **Credentials in `.env` only** — never in the Claude Desktop config
- **Read-only transactions** — SELECT queries run inside `readonly=True` transactions
- **Input validation** — table/schema names validated with regex to prevent injection
- **No DDL** — DROP, CREATE, ALTER are always blocked even when writes are enabled
- **`.env` excluded from git** — credentials never committed

---

## 📁 Project Structure

```
Cluade-MCP-PostgreSQL/
├── main.py                    # 🚀 MCP server entry point (FastMCP + stdio)
├── database.py                # 🔌 Async connection pool (asyncpg)
├── tools/
│   ├── __init__.py
│   ├── schema_tools.py        # list_schemas, list_tables, describe_table, search_schema, list_indexes
│   ├── query_tools.py         # execute_query, get_table_sample, get_table_stats, explain_query
│   ├── write_tools.py         # execute_write (opt-in)
│   └── database_tools.py     # get_database_info, list_databases
├── .env                       # ✅ Your credentials (NOT committed to git)
├── .env.example               # Template for new users
├── .gitignore                 # Excludes .env, .venv, __pycache__
├── requirements.txt           # mcp[cli], asyncpg, python-dotenv, pydantic, orjson
├── claude_desktop_config.json # Example Claude Desktop config snippet
└── README.md
```

---

## ⚙️ Environment Variables

All configuration is done via `.env`:

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | — | Database name |
| `DB_USER` | — | Database user |
| `DB_PASSWORD` | — | Database password |
| `DB_MIN_CONNECTIONS` | `1` | Min pool connections |
| `DB_MAX_CONNECTIONS` | `10` | Max pool connections |
| `ALLOW_WRITE_OPERATIONS` | `false` | Enable INSERT/UPDATE/DELETE |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING) |

---

## 🛠️ Troubleshooting

### Claude doesn't see the MCP server
- Fully quit and reopen Claude Desktop after editing the config
- Check the `cwd` path — it must point to the project folder
- Verify the `.venv` Python path is correct: `.venv\Scripts\python.exe`

### Connection refused / authentication failed
- Check your `.env` credentials match your PostgreSQL setup
- Test directly: `psql -h localhost -U your_user -d your_db`
- Ensure PostgreSQL is running: `pg_isready`

### `mcp` or `asyncpg` module not found
```bash
.venv\Scripts\pip install -r requirements.txt
```

### Server starts but tools don't appear in Claude
- Open Claude Desktop → Settings → Developer → MCP Servers
- Check for error messages next to the `postgres` server entry
- Run `python main.py` manually and check stderr for import errors

---

## 📋 Requirements

- Python 3.10+
- PostgreSQL 12+
- Claude Desktop (with MCP support)

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🤝 Contributing

Pull requests welcome! Please fork the repo, create a feature branch, and submit a PR with a clear description.
# PostgreSQL-MCP
