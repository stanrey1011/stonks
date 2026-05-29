#!/usr/bin/env bash
# Scan signals and post to Discord before the trading day opens.
# Runs at 13:00 UTC (3:00am HST / 9:00am ET) weekdays — 30 min before market open.
# Crontab: 0 13 * * 1-5 /home/as/stonks/scripts/daily_alert.sh
#
# Depends on daily_pipeline.sh having run after the previous close (20:30 UTC).

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
    ${STONKS_DISCORD_WEBHOOK:+--webhook-url "$STONKS_DISCORD_WEBHOOK"} \
    >> "$LOG" 2>&1

# ── weekly signals (confluence ≥2) ───────────────────────────────────────────
"$VENV" alert all --all-strategies --interval 1wk \
    --min-signals 2 \
    ${STONKS_DISCORD_WEBHOOK:+--webhook-url "$STONKS_DISCORD_WEBHOOK"} \
    >> "$LOG" 2>&1

# ── LEAP scan ─────────────────────────────────────────────────────────────────
"$VENV" leaps all --interval 1wk \
    ${STONKS_DISCORD_WEBHOOK:+--webhook-url "$STONKS_DISCORD_WEBHOOK"} \
    >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Done" >> "$LOG"
