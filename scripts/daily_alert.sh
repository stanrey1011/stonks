#!/usr/bin/env bash
# Daily alert scan — runs after market close, checks all tickers across all strategies
# Schedule: crontab -e → 30 20 * * 1-5 /home/as/stonks/scripts/daily_alert.sh
# (20:30 UTC = 4:30pm ET, weekdays only)
#
# Set STONKS_DISCORD_WEBHOOK in your environment or .env file

set -euo pipefail

STONKS_DIR="/home/as/stonks"
VENV="$STONKS_DIR/venv/bin/stonks"
LOG="$STONKS_DIR/log/daily_alert.log"

# Load webhook from .env if present
ENV_FILE="$STONKS_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') — Starting daily alert scan" >> "$LOG"

# Fetch fresh data first, then scan
"$VENV" fetch --all-tickers --interval 1d >> "$LOG" 2>&1
"$VENV" clean --all-tickers --interval 1d >> "$LOG" 2>&1

"$VENV" alert \
    --all-strategies \
    --all-tickers \
    --interval 1d \
    --use-optimized \
    ${STONKS_DISCORD_WEBHOOK:+--webhook-url "$STONKS_DISCORD_WEBHOOK"} \
    >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Done" >> "$LOG"
