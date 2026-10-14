# Docker Guide — PostgreSQL MCP Server

How this server runs in Docker, and exactly what to do when you change something.

---

## How it's wired up

- **Image** `postgres-mcp` — built from the `Dockerfile`. Contains the Python code and dependencies. Only needs rebuilding when code changes.
- **Container** `postgres-mcp-server` — a single, named, persistent container created from that image. Claude Desktop starts and stops this *same* container every time instead of creating a new one — no container churn.
- **Claude Desktop's config** (`claude_desktop_config.json`, the one under `%APPDATA%\Claude` / the app's package folder — not the copy in this repo, which is just a reference) launches it with:
  ```json
  "postgres": {
    "command": "docker",
    "args": ["start", "-ai", "postgres-mcp-server"]
  }
  ```
  This starts the existing container and attaches to its stdio. When Claude Desktop is fully quit, the container stops (but is **not** deleted) — ready to be started again next time.

- **`.env`** holds DB credentials (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) plus `ALLOW_WRITE_OPERATIONS` and `LOG_LEVEL`. These are baked into the container **at creation time** via `--env-file .env` — not read live. Changing `.env` requires recreating the container (see below), not rebuilding the image.

---

## The one rule that matters

| What changed | Rebuild image? | Recreate container? |
|---|:---:|:---:|
| `.env` (password, host, write flag, etc.) | ❌ No | ✅ Yes |
| `main.py` / `database.py` / `tools/*.py` | ✅ Yes | ✅ Yes |
| `requirements.txt` | ✅ Yes | ✅ Yes |
| `Dockerfile` | ✅ Yes | ✅ Yes |

Env vars are a container-creation-time snapshot. Code is an image-build-time snapshot. Neither is read live from disk once the container exists.

---

## Strategy 1 — `.env` changed only

No image rebuild needed.

```bash
# 1. Quit Claude Desktop fully (system tray → Quit, not just closing the window)

# 2. Remove the old container
docker stop postgres-mcp-server
docker rm postgres-mcp-server

# 3. Recreate it with the updated .env
cd "path/to/Claude-Desktop-to-PostgreSQL-main"
docker create --name postgres-mcp-server -i --env-file ".env" postgres-mcp

# 4. Reopen Claude Desktop
```

> Add `-e DB_HOST=host.docker.internal` to the `docker create` line **only** if `.env`'s `DB_HOST` is `localhost` (i.e. you're pointing at Postgres running on this same Windows machine). Skip it entirely if `DB_HOST` is already a real reachable address (a remote VM's IP, etc.) — `host.docker.internal` only exists to let a container reach back out to its own host machine, and is meaningless/wrong for a remote database.

---

## Strategy 2 — code changed

(`main.py`, `database.py`, `tools/*.py`, `requirements.txt`, or `Dockerfile`)

```bash
# 1. Quit Claude Desktop fully (system tray → Quit)

# 2. Remove the old container
docker stop postgres-mcp-server
docker rm postgres-mcp-server

# 3. Rebuild the image
cd "path/to/Claude-Desktop-to-PostgreSQL-main"
docker build -t postgres-mcp .

# 4. Recreate the container from the new image
docker create --name postgres-mcp-server -i --env-file ".env" postgres-mcp

# 5. Reopen Claude Desktop
```

Same as Strategy 1, plus the `docker build` step before recreating.

---

## Verifying before reopening Claude Desktop (optional but recommended)

```bash
docker start -ai postgres-mcp-server
```

Watch the log output. You want to see:
```
✅ Database connection pool ready.
```
with no `❌` error lines. Press `Ctrl+C` to stop it — this puts the container back to "Exited", ready for Claude Desktop to start normally.

If you see an error instead, common causes:
- `password authentication failed for user "..."` — wrong `DB_PASSWORD` in `.env`, or the user/database doesn't exist yet
- Connection timeout / refused — wrong `DB_HOST`/`DB_PORT`, or a firewall/NSG blocking the connection (for remote DBs, check the DB server's firewall rules allow this machine's IP)

---

## Useful diagnostic commands

```bash
# Is the container currently running?
docker ps -a --filter "name=postgres-mcp-server" --format "table {{.Names}}\t{{.Status}}"

# Is the image built and how old is it?
docker images postgres-mcp --format "table {{.ID}}\t{{.CreatedSince}}\t{{.Size}}"

# Tail the container's logs (if it's running)
docker logs -f postgres-mcp-server
```

---

## Why a persistent named container instead of `docker run --rm`?

Earlier versions of this setup used `docker run -i --rm ... postgres-mcp`, which creates a brand-new container every time Claude Desktop launches and deletes it on exit. That works, but means constant container churn. The current approach (`docker create` once, then `docker start -ai` repeatedly) reuses the same container — faster startup, no churn, and its identity/logs persist across sessions until you explicitly remove it as part of a rebuild.

## Why not run this over HTTP instead of stdio?

We tried switching to `streamable-http` transport so the container's lifecycle could be fully decoupled from Claude Desktop (start/stop independently, connect via Claude Desktop's "Add custom connector" URL field). This hit a hard blocker: Claude Desktop's custom connector form requires the URL to start with `https://`, and this server has no TLS support built in. Making that work would require a locally-trusted certificate (e.g. via `mkcert`) and either TLS termination inside the app or a reverse proxy in front of it — meaningfully more infrastructure than the stdio approach for no functional gain here. There is no `docker-compose.yml` in this project — only the single named container (`postgres-mcp-server`) described above, to avoid two containers existing side by side.
