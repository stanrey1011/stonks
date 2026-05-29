# Docker Deployment Guide & Hardening Plan

> Working document. Goal: turn the existing Docker scaffolding into a clean,
> portable, deployable setup. Written to be picked up cold in a later session
> (possibly by a different model). Read this top-to-bottom before changing files.

---

## 1. Context — how the app runs today

`stonks` is a local-first quantitative trading toolkit (Python 3.13). Three
long-lived processes plus scheduled batch jobs:

| Process | Command | Notes |
|---|---|---|
| Web dashboard | `stonks dash` → `streamlit run stonkslib/dash/app.py` (port **8501**) | `stonkslib/cli/dash.py` shells out to streamlit |
| Discord bot | `stonks bot` | `stonkslib/bot/discord_bot.py` calls `client.run(token)` at module level (no `__main__` guard) |
| Scheduled jobs | pipeline / alert / optimize / earnings-refresh | see schedules below |

**Today on the host (`Anton`)** these run as **systemd user units** (not Docker):
`stonks-dash.service`, `stonks-bot.service`, and four timers
(`stonks-pipeline`, `stonks-alert`, `stonks-optimize`, `stonks-earnings`). The
timer services call shell scripts in `scripts/` that hardcode
`/home/as/stonks/venv/bin/stonks`.

**External dependencies:** Ollama (LLM optimize + chat + interpreter), and these
HTTP APIs via keys in `.env`: Finnhub, Discord webhook/bot, Alpaca, SnapTrade.

**Python version is load-bearing:** must be **3.13** (3.14 breaks numpy; the
SnapTrade SDK breaks on 3.13 so we hand-rolled a `requests`-only client — see
`stonkslib/broker/snaptrade.py`). Keep the base image on `python:3.13-*`.

---

## 2. Current Docker state (what already exists, uncommitted)

All four are untracked in git — commit them once this plan is executed.

- **`Dockerfile`** — `python:3.13-slim`; installs `gcc/g++/curl` + **supercronic**
  (container-native cron); `pip install` of `requirements.txt` (strips the `-e`
  editable line) then `pip install -e .`; `EXPOSE 8501`; CMD runs streamlit.
- **`docker-compose.yml`** — three services (`stonks-dash`, `stonks-bot`,
  `stonks-scheduler`) all building the same image, **all bind-mounting `.:/app`**,
  `env_file: .env`, `OLLAMA_HOST` → `host.docker.internal:11434`,
  `restart: unless-stopped`. Bot runs `python stonkslib/bot/discord_bot.py`;
  scheduler runs `supercronic /app/docker/crontab`.
- **`docker/crontab`** — supercronic schedule (UTC), calls `stonks ...` directly
  (does NOT use the `scripts/*.sh` wrappers — good).
- **`.dockerignore`** — excludes `venv/ __pycache__ *.pyc *.pyo data/ log/ .env .git/`.

### Schedules (keep these in sync wherever they live)

| Job | Schedule (UTC) | Command |
|---|---|---|
| pipeline | Mon–Fri 20:00 | `stonks pipeline all --interval 1d` then `1wk` |
| alert | Mon–Fri 20:30 | `stonks alert all … 1d` + `1wk` + `stonks leaps all 1wk` |
| optimize p1 | Mon–Fri 10:00 | `stonks optimize … --model qwen2.5:7b` (1d, 1wk) |
| optimize p2 | Mon–Fri 11:00 | `stonks optimize … --model qwen2.5:32b --warm-start` |
| earnings | Sat,Sun 12:00 | `stonks earnings-refresh` |

> Note: the host **systemd** optimizer runs both phases sequentially in one script
> (`scripts/nightly_optimize.sh`); the **container crontab** splits them into two
> cron lines (10:00 and 11:00). If phase 1 runs past 11:00, the two overlap. See
> task P1-4.

---

## 3. Target architecture

```
┌──────────────────────────── docker compose ────────────────────────────┐
│  stonks-dash      (Streamlit :8501, healthcheck /_stcore/health)        │
│  stonks-bot       (Discord bot, long-lived)                              │
│  stonks-scheduler (supercronic → stonks CLI batch jobs)                  │
│        │  all share one image (code baked in, NOT bind-mounted)          │
│        └── named volumes:  stonks-data → /app/data                       │
│                            stonks-log  → /app/log                        │
└──────────────────────────────────────────────────────────────────────────┘
              │ OLLAMA_HOST
              ▼
   Ollama  (host process OR separate container — DECISION, §6)
```

Principle: **one image, code baked in; only `data/` and `log/` are volumes; all
config/secrets via `.env`.** No host path dependencies → runs on any Docker host.

---

## 4. Gaps to fix — prioritized

### P0 — required for a genuine deployable image

**P0-1. Drop the `.:/app` bind mount; bake code into the image.**
- Today `volumes: - .:/app` mounts the host repo over `/app`, shadowing the
  image's baked code. The image is not self-contained and requires the full repo
  on the host. This is a dev convenience, not a deploy artifact.
- **Do:** remove the source bind mount from the production compose. Keep ONLY
  named volumes for `data/` and `log/`. Provide a separate
  `docker-compose.override.yml` for dev that re-adds `.:/app` (Compose merges it
  automatically when present, so `docker compose up` = dev, and
  `docker compose -f docker-compose.yml up` = prod).

**P0-2. Persist `data/` and `log/` via named volumes + ensure writability.**
- `data/` holds everything stateful: cleaned parquet, analysis CSVs, backtest
  results, earnings/news caches, `data/last_alert.json`, and **the SnapTrade
  credential `data/snaptrade_user.json`** (chmod 600, holds the userSecret). This
  MUST persist across `docker compose down/up`.
- `log/` receives the crontab job logs (`/app/log/*.log`).
- Both are `.dockerignore`d (correct — don't bake them in) but currently only
  survive because of the `.:/app` bind mount. After P0-1 they need real volumes.
- **Do:** in compose add
  ```yaml
  volumes:
    stonks-data:
    stonks-log:
  ```
  and mount on each service:
  ```yaml
    volumes:
      - stonks-data:/app/data
      - stonks-log:/app/log
  ```
  In the Dockerfile, create the dirs so they exist even before the volume is
  populated and are owned by the runtime user (see P1-1):
  ```dockerfile
  RUN mkdir -p /app/data /app/log
  ```

**P0-3. Pick ONE source of truth for schedules.**
- Schedules currently live in BOTH host systemd timers and `docker/crontab`.
  Maintaining both drifts (already: optimize phase split differs; a stale comment
  in `scripts/daily_alert.sh` says 13:00 while the timer is 20:30).
- **Decision (see §6):** if deploying via Docker, the `stonks-scheduler` container
  (supercronic) becomes the source of truth → **disable the host systemd timers**
  (`systemctl --user disable --now stonks-{pipeline,alert,optimize,earnings}.timer`)
  to avoid double-runs. If staying on host systemd and only containerizing
  dash+bot, then DROP the scheduler service from compose instead.

**P0-4. `scripts/*.sh` are host-only — keep them out of the container path.**
- `scripts/nightly_pipeline.sh`, `daily_alert.sh`, etc. hardcode
  `STONKS_DIR=/home/as/stonks` and `$VENV=…/venv/bin/stonks` — neither exists in
  the container. The crontab already bypasses them (calls `stonks` directly), so
  no action needed EXCEPT: do not “helpfully” wire these scripts into the
  container. Optionally add a header comment marking them host/systemd-only.

**P0-5. Verify `OLLAMA_HOST` actually reaches Ollama from the container.**
- Compose sets `OLLAMA_HOST=http://host.docker.internal:11434`, but a grep of
  `stonkslib/llm/*` and `stonkslib/cli/*` found **no code reading `OLLAMA_HOST`**.
  The `ollama` Python lib reads `OLLAMA_HOST` from the env *by default*, so it may
  work — but this is unverified and the optimize/chat features silently no-op or
  error if it doesn't.
- **Do:** confirm how the optimizer constructs its client
  (`stonkslib/llm/optimizer.py`, `stonkslib/llm/interpreter.py`). If it calls
  `ollama.Client()` with no args, the env var is honored. If it hardcodes a host
  or uses `ollama.chat(...)` module-level, confirm that path respects the env. If
  not, pass `host=os.getenv("OLLAMA_HOST")` explicitly. Test from inside the
  container: `docker compose exec stonks-scheduler python -c "import ollama; print(ollama.list())"`.

### P1 — hardening / quality

**P1-1. Run as a non-root user.** Add a `useradd` and `USER` in the Dockerfile;
`chown` `/app/data` and `/app/log`. Named-volume perms: first run as root to
`chown`, or set the volume owner via an entrypoint. Simplest: create user
`stonks` (uid 1000), `chown -R stonks:stonks /app`, `USER stonks`.

**P1-2. Healthchecks.** Dash has a health endpoint:
```yaml
  healthcheck:
    test: ["CMD", "curl", "-fsS", "http://localhost:8501/_stcore/health"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 20s
```
(`curl` is already installed in the image.) Bot/scheduler have no natural HTTP
probe — optionally a process/file-based check or skip.

**P1-3. Multi-stage build to slim the final image.** Build wheels in a builder
stage with `gcc/g++`, then copy site-packages into a clean `python:3.13-slim`
runtime without compilers. Keeps `curl` + `supercronic` in runtime. Reduces image
size and attack surface.

**P1-4. Fix optimize phase overlap.** Either (a) combine both phases into one cron
line chained with `&&` (mirrors the systemd script, guarantees ordering), or
(b) give phase 1 enough headroom. Recommend (a):
```cron
0 10 * * 1-5 stonks optimize … 7b 1d && … 7b 1wk && … 32b --warm-start 1d && … 32b --warm-start 1wk >> /app/log/optimize.log 2>&1
```

**P1-5. Standardize the bot launch command.** Compose uses
`python stonkslib/bot/discord_bot.py`; systemd uses `stonks bot`. Use `stonks bot`
in compose for consistency (and because the module runs `client.run` at import,
which is fragile). Verify `stonks bot` works in-container.

**P1-6. Add `.env.example`.** `.gitignore` now allows `!.env.example`. List every
required var with placeholder values (see §7) so a fresh deploy knows what to set.

**P1-7. Pin the base image** by digest (`python:3.13-slim@sha256:…`) for
reproducible builds; review `.dockerignore` (add `*.md`, `tests/`, `charts/`,
`.git*`, `DOCKER_DEPLOYMENT.md` itself if you don't want it in the image).

**P1-8. Slim `requirements.txt` after the SnapTrade migration.** Once
`broker/robinhood.py` is migrated off `robin_stocks` (in progress), remove
`robin_stocks` and `pyotp` (and orphaned `cryptography`/`cffi` bump if unused) so
the image doesn't install the abandoned Robinhood path.

### P2 — optional / nice-to-have

- **P2-1. Containerize Ollama** as a compose service (`ollama/ollama` image, GPU
  via `deploy.resources.reservations.devices`, model volume). Heavy: `qwen2.5:32b`
  needs ~20GB+ RAM/VRAM. Otherwise document the external-host requirement.
- **P2-2. Resource limits** (`deploy.resources.limits`), log rotation
  (`logging: driver: json-file, options: max-size/max-file`).
- **P2-3. CI** to build and push the image to a registry; tag by git SHA.
- **P2-4. Secrets** beyond `.env`: consider Docker secrets / a vault if this ever
  leaves a single trusted host.

---

## 5. Concrete file changes (suggested end-state)

### `docker-compose.yml` (production — no source bind mount)
```yaml
services:
  stonks-dash:
    build: .
    image: stonks:latest
    container_name: stonks-dash
    ports: ["8501:8501"]
    env_file: .env
    environment:
      - OLLAMA_HOST=${OLLAMA_HOST:-http://host.docker.internal:11434}
    extra_hosts: ["host.docker.internal:host-gateway"]
    volumes:
      - stonks-data:/app/data
      - stonks-log:/app/log
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    restart: unless-stopped

  stonks-bot:
    build: .
    image: stonks:latest
    container_name: stonks-bot
    env_file: .env
    environment:
      - OLLAMA_HOST=${OLLAMA_HOST:-http://host.docker.internal:11434}
    extra_hosts: ["host.docker.internal:host-gateway"]
    volumes:
      - stonks-data:/app/data
      - stonks-log:/app/log
    command: stonks bot
    restart: unless-stopped

  stonks-scheduler:
    build: .
    image: stonks:latest
    container_name: stonks-scheduler
    env_file: .env
    environment:
      - OLLAMA_HOST=${OLLAMA_HOST:-http://host.docker.internal:11434}
    extra_hosts: ["host.docker.internal:host-gateway"]
    volumes:
      - stonks-data:/app/data
      - stonks-log:/app/log
    command: supercronic /app/docker/crontab
    restart: unless-stopped

volumes:
  stonks-data:
  stonks-log:
```

### `docker-compose.override.yml` (dev — auto-merged by `docker compose up`)
```yaml
# Re-adds live source mounting + build for local iteration. Not used in prod.
services:
  stonks-dash:
    volumes:
      - .:/app
      - stonks-data:/app/data   # keep data on the named volume even in dev
      - stonks-log:/app/log
  stonks-bot:
    volumes: [".:/app", "stonks-data:/app/data", "stonks-log:/app/log"]
  stonks-scheduler:
    volumes: [".:/app", "stonks-data:/app/data", "stonks-log:/app/log"]
```
> Prod run: `docker compose -f docker-compose.yml up -d` (override ignored).
> Dev run: `docker compose up` (override merged).

### `Dockerfile` (multi-stage + non-root sketch)
```dockerfile
# ---- builder ----
FROM python:3.13-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN grep -v '^\s*-e\s' requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir --prefix=/install -r /tmp/req.txt

# ---- runtime ----
FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
ARG SUPERCRONIC_VERSION=0.2.33
RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic && chmod +x /usr/local/bin/supercronic
COPY --from=builder /install /usr/local
COPY pyproject.toml tickers.yaml config.yaml ./
COPY stonkslib/ stonkslib/
COPY docker/ docker/
RUN pip install --no-cache-dir -e . \
    && mkdir -p /app/data /app/log \
    && useradd -u 1000 -m stonks && chown -R stonks:stonks /app
USER stonks
EXPOSE 8501
CMD ["stonks", "dash", "--host", "0.0.0.0", "--port", "8501"]
```
> Verify `stonks dash` accepts `--host/--port` (see `stonkslib/cli/dash.py`,
> signature `dash(port, host)`); if the flags differ, fall back to the explicit
> `streamlit run … --server.address=0.0.0.0 --server.port=8501 --server.headless=true`.

---

## 6. Decisions to make before implementing

1. **Where does this deploy?** Same host as today, or a remote box / VPS? (Affects
   whether `host.docker.internal` for Ollama is reachable and whether systemd
   timers must be disabled.)
2. **Ollama: host or container?** Host (current; keep `host.docker.internal`) is
   simplest if a GPU box already runs Ollama. Container is portable but needs GPU
   passthrough + a model volume + ~20GB for `qwen2.5:32b`. If the deploy target
   has no Ollama, the optimize/chat features won't work until this is resolved.
3. **Scheduler: container supercronic vs host systemd?** Don't run both (double
   execution). Recommend: containerize → disable host timers (P0-3).
4. **Dev vs prod compose split?** Confirm the override-file approach (§5) vs a
   single file. Override keeps `docker compose up` ergonomic for local work.

---

## 7. Required environment variables (for `.env` / `.env.example`)

```
# Discord
STONKS_DISCORD_WEBHOOK=
DISCORD_BOT_TOKEN=
# Market data
FINNHUB_API_KEY=
# Alpaca (paper required; live optional)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_PAPER=true
ALPACA_LIVE_API_KEY=
ALPACA_LIVE_SECRET_KEY=
# SnapTrade (Robinhood via aggregator)
SNAPTRADE_CLIENT_ID=
SNAPTRADE_CONSUMER_KEY=
# Ollama (LLM) — host reachable from the container
OLLAMA_HOST=http://host.docker.internal:11434
```
> `data/snaptrade_user.json` (the SnapTrade userSecret) is generated at runtime,
> NOT an env var — it lives on the `stonks-data` volume.

---

## 8. Verification / test plan

1. **Build:** `docker compose -f docker-compose.yml build` (clean, no cache:
   `--no-cache` once).
2. **Up:** `docker compose -f docker-compose.yml up -d` → `docker compose ps`
   shows all three healthy/running.
3. **Dash:** `curl -fsS http://localhost:8501/_stcore/health` → `ok`; open the UI,
   confirm pages render (Alpaca, Robinhood, Watchlist, Chart).
4. **Bot:** `docker compose logs stonks-bot` shows "logged in"; issue `!help` in
   Discord.
5. **Ollama reachability:** `docker compose exec stonks-scheduler python -c "import ollama, os; print(os.getenv('OLLAMA_HOST')); print([m['model'] for m in ollama.list()['models']])"`.
6. **Manual job run (don't wait for cron):**
   `docker compose exec stonks-scheduler stonks pipeline AAPL --interval 1d` →
   check `docker compose exec stonks-scheduler ls -la /app/data/ticker_data/clean/AAPL`.
7. **Persistence:** `docker compose down && docker compose -f docker-compose.yml up -d`
   → confirm `data/` survived (watchlist, snaptrade_user.json, caches still there).
8. **Scheduler:** `docker compose logs stonks-scheduler` shows supercronic parsed
   the crontab and scheduled all 5 jobs.
9. **Non-root:** `docker compose exec stonks-dash whoami` → `stonks`.

---

## 9. Suggested execution order

1. Decisions in §6 (especially Ollama + scheduler source-of-truth).
2. P0-5 (verify/fix OLLAMA_HOST) — cheap, unblocks LLM features.
3. P0-1 + P0-2 (compose: drop bind mount, add named volumes) + override file.
4. P0-3 (disable host timers if containerizing the scheduler).
5. P1-1 (non-root) + P1-2 (healthcheck) + Dockerfile multi-stage (P1-3).
6. P1-4/5 (crontab phases, bot command), P1-6 (`.env.example`).
7. Full §8 verification.
8. Commit the Docker artifacts (Dockerfile, compose, override, docker/crontab,
   .dockerignore, .env.example, this doc).
9. P1-8 (slim requirements) after the SnapTrade/Robinhood adapter is finished.

---

## 10. Open follow-ups from the broker work (related, not blocking Docker)

- The Robinhood integration via SnapTrade is **mid-flight**: `broker/snaptrade.py`
  (signed REST client) is built and a SnapTrade user is registered; the Robinhood
  brokerage connection through the SnapTrade portal still needs to be completed,
  then `broker/robinhood.py` rewritten as a SnapTrade adapter. The `data/`
  volume must carry `snaptrade_user.json` for this to keep working in a container.
```
