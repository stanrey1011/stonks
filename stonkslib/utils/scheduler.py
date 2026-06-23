"""Optimize scheduler — detached run-now jobs + JSON-defined recurring schedules.

**Docker-native by design.** The dashboard and the scheduler both run in
containers (anton dev and .208 prod), so there is no host systemd to drive — the
prod scheduler is supercronic running `docker/crontab`. This module therefore:

- Stores schedules in `data/optimize_schedules.json` (the `data/` volume is
  gitignored, so schedules survive `git pull` and never diverge from git).
- Lets the dashboard CRUD that file (no systemd, no crontab editing from the GUI).
- Exposes `tick()`, invoked once a minute by `stonks scheduler-tick` (a single
  committed line in `docker/crontab`, run by supercronic in the stonks-scheduler
  container). `tick()` launches any schedule whose UTC day/time matches now, as a
  detached background process — so a multi-hour optimize never blocks the next tick.

Detached runs use `stonks optimize …` (resolved via PATH), so they appear in
`utils/jobs.list_jobs()` and are cancellable from the Running-jobs panel. All
schedule times are UTC.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STONKS_BIN = shutil.which("stonks") or str(PROJECT_ROOT / "venv" / "bin" / "stonks")
DATA_DIR = PROJECT_ROOT / "data"
SCHEDULES_FILE = DATA_DIR / "optimize_schedules.json"
LOG_DIR = PROJECT_ROOT / "log" / "opt_runs"

VALID_CATEGORIES = ("stocks", "etfs", "crypto")
# ISO weekday: 1=Mon … 7=Sun
WEEKDAYS = [(1, "Mon"), (2, "Tue"), (3, "Wed"), (4, "Thu"), (5, "Fri"), (6, "Sat"), (7, "Sun")]


# ── command building ────────────────────────────────────────────────────────────

def build_optimize_args(
    strategy_files: list[str],
    *,
    all_strategies: bool = False,
    target: str = "all",          # "all" or a single TICKER
    model: str = "qwen2.5:7b",
    interval: str = "1d",
    iterations: int = 3,
    per_ticker: bool = False,
    leaps: bool = False,
    option_type: str = "auto",
) -> list[str]:
    """The `stonks` argv *after* the binary (i.e. starts with 'optimize'). Stored
    in schedules and prefixed with STONKS_BIN at launch — keeps stored schedules
    portable across containers where the binary path differs."""
    args: list[str] = ["optimize", "--interval", interval,
                       "--iterations", str(iterations), "--model", model]
    if all_strategies:
        args.append("--all-strategies")
    else:
        for fn in strategy_files:
            args += ["--strategy", fn]
    args.append("--all-tickers" if target == "all" else "--ticker")
    if target != "all":
        args.append(target.upper())
    if per_ticker:
        args.append("--per-ticker")
    if leaps:
        args += ["--leaps", "--option-type", option_type]
    return args


# ── detached run-now ────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "unnamed"


def run_detached(opt_args: list[str], label: str = "optimize") -> dict:
    """Launch `stonks <opt_args>` detached, logging to a file. Returns
    {"pid", "log"}. setsid'd so a Streamlit rerun can't reap it."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"{ts}_{_slug(label)}.log"
    full = [str(STONKS_BIN), *[str(a) for a in opt_args]]
    f = open(log_path, "ab", buffering=0)
    f.write(f"# {' '.join(full)}\n".encode())
    proc = subprocess.Popen(
        full, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True, cwd=str(PROJECT_ROOT),
    )
    return {"pid": proc.pid, "log": str(log_path)}


def recent_logs(limit: int = 20) -> list[Path]:
    if not LOG_DIR.exists():
        return []
    return sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def tail(path: str | Path, n: int = 300) -> str:
    try:
        with open(path) as f:
            return "".join(f.readlines()[-n:])
    except Exception as e:
        return f"(could not read log: {e})"


# ── schedule store (JSON in the data volume) ────────────────────────────────────

def _load() -> list[dict]:
    try:
        return json.loads(SCHEDULES_FILE.read_text()).get("schedules", [])
    except Exception:
        return []


def _save(scheds: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SCHEDULES_FILE.write_text(json.dumps({"schedules": scheds}, indent=2))


def list_schedules() -> list[dict]:
    return _load()


def create_schedule(name: str, days: list[int], hour: int, minute: int,
                    opt_args: list[str]) -> dict:
    """Create/replace a schedule (upsert by slug). `days` are ISO weekdays (1-7),
    `hour`/`minute` are UTC. Returns {"ok", "id"}."""
    sid = _slug(name)
    scheds = [s for s in _load() if s["id"] != sid]
    scheds.append({
        "id": sid, "name": name, "days": sorted(set(int(d) for d in days)),
        "hour": int(hour), "minute": int(minute), "args": opt_args,
        "enabled": True, "created": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
    })
    _save(scheds)
    return {"ok": True, "id": sid}


def set_enabled(sid: str, on: bool) -> None:
    scheds = _load()
    for s in scheds:
        if s["id"] == sid:
            s["enabled"] = bool(on)
    _save(scheds)


def delete_schedule(sid: str) -> None:
    _save([s for s in _load() if s["id"] != sid])


def next_run(sched: dict, now: datetime | None = None) -> datetime | None:
    """Next UTC firing of a schedule, or None if it has no days."""
    days = sched.get("days") or []
    if not days:
        return None
    now = now or datetime.now(timezone.utc)
    for d in range(0, 8):
        cand = (now + timedelta(days=d)).replace(
            hour=int(sched["hour"]), minute=int(sched["minute"]), second=0, microsecond=0)
        if cand.isoweekday() in days and cand > now:
            return cand
    return None


# ── dispatcher (called by `stonks scheduler-tick` via supercronic) ──────────────

def due_now(now: datetime | None = None) -> list[dict]:
    """Enabled schedules matching the current UTC minute (not already fired this minute)."""
    now = now or datetime.now(timezone.utc)
    iso_wd = now.isoweekday()
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    out = []
    for s in _load():
        if not s.get("enabled"):
            continue
        if iso_wd not in (s.get("days") or []):
            continue
        if int(s["hour"]) == now.hour and int(s["minute"]) == now.minute and s.get("last_run") != stamp:
            out.append(s)
    return out


def _mark_run(sid: str, stamp: str) -> None:
    scheds = _load()
    for s in scheds:
        if s["id"] == sid:
            s["last_run"] = stamp
    _save(scheds)


def tick() -> list[dict]:
    """Launch all schedules due this minute (detached). Returns what was launched."""
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M")
    launched = []
    for s in due_now(now):
        info = run_detached(s["args"], label=s["id"])
        _mark_run(s["id"], stamp)
        launched.append({"id": s["id"], **info})
    return launched
