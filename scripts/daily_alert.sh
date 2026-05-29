#!/usr/bin/env bash
# HOST-ONLY: runs on Anton via systemd stonks-alert.timer (not used inside Docker).
# Scan signals and log results. Notifications go to Matrix (configured in Phase B).
# Runs at 20:30 UTC (after pipeline at 20:00 UTC) Mon-Fri.

set -euo pipefail

STONKS_DIR="/home/as/stonks"
VENV="$STONKS_DIR/venv/bin/stonks"
LOG="$STONKS_DIR/log/daily_alert.log"

if [[ -f "$STONKS_DIR/.env" ]]; then
    export $(grep -v '^#' "$STONKS_DIR/.env" | xargs)
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') — Starting alert scan" >> "$LOG"

# ── daily signals (confluence ≥2, weekly trend must agree) ───────────────────
"$VENV" alert all --all-strategies --interval 1d \
    --min-signals 2 --confirm-weekly \
    >> "$LOG" 2>&1

# ── weekly signals (confluence ≥2) ───────────────────────────────────────────
"$VENV" alert all --all-strategies --interval 1wk \
    --min-signals 2 \
    >> "$LOG" 2>&1

# ── LEAP scan ─────────────────────────────────────────────────────────────────
"$VENV" leaps all --interval 1wk \
    >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Done" >> "$LOG"
