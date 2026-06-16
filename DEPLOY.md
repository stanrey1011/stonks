# Deployment workflow

**One rule:** develop on **anton**, publish to **git**, pull on **production (.208)**.
Production is **pull-only** — never edit files directly on .208. Direct edits on prod are
what caused the great divergence of June 2026; don't reintroduce them.

```
   anton (dev)                GitHub (main)              .208 (prod)
   ───────────                ─────────────              ───────────
   edit + test  ──push──▶     origin/main   ──pull──▶    docker compose up -d
```

## Develop (anton)

```sh
cd ~/homelab/apps/stonks
# edit code, run tests
python dev/test_engine.py
git add -A && git commit -m "…"
git push origin main
```

The watchlist (`tickers.yaml`) is tracked in git — **edit it on anton and push**, don't
change it on prod (a local edit on .208 would conflict with the next pull). Use
`stonks tickers …` locally, or edit the file directly.

## Deploy (.208)

```sh
ssh as@10.11.87.208
cd ~/homelab/apps/stonks
git pull                       # fast-forward main
docker compose up -d           # picks up new code (source is bind-mounted)
```

- The source tree is bind-mounted into the containers (`.:/app` via
  `docker-compose.override.yml`), so a pull + `up -d` is enough — **no rebuild** unless
  `requirements.txt` / `Dockerfile` changed (then `up -d --build`).
- The scheduler is gated behind the `scheduler` profile; `.208`'s `.env` sets
  `COMPOSE_PROFILES=scheduler` so `up -d` starts both `stonks-dash` and `stonks-scheduler`.
- Gitignored state survives pulls untouched: `data/`, `strategies/optimized/`, `.env`,
  `data/snaptrade_user.json` (the SnapTrade/Robinhood link).

## Verify after deploy

```sh
docker compose ps                                   # both containers healthy
curl -fsS http://localhost:8501/_stcore/health      # dashboard up
docker compose exec stonks-dash python -c "import stonkslib.strategies.engine; print('ok')"
docker compose logs --since 5m stonks-scheduler
```

## Running a dev copy on anton at the same time

Safe to run a test instance on anton while prod runs on .208 — they keep separate data
stores. Guardrails on the anton copy:
- **Don't** set `COMPOSE_PROFILES=scheduler` (run dashboard only — no duplicate cron jobs).
- Leave `STONKS_DISCORD_WEBHOOK` unset (no duplicate alerts).
- `ALPACA_PAPER=true`; never run live execution from the dev copy.
- Reuse the existing `SNAPTRADE_USER_ID` / `SNAPTRADE_USER_SECRET` — **never re-register**
  from anton (that rotates the secret and breaks prod's Robinhood link).
