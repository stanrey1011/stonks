#!/usr/bin/env bash
# Weekend earnings cache refresh.
# Keeps next-earnings dates and EPS estimates current over the weekend
# so the Watchlist and Chart overlays are fresh on Monday morning.
#
# Scheduled via stonks-earnings.timer (Sat-Sun 12:00 UTC).

set -euo pipefail

STONKS_DIR="/home/as/stonks"
VENV="$STONKS_DIR/venv/bin/stonks"
LOG="$STONKS_DIR/log/earnings.log"

mkdir -p "$STONKS_DIR/log"

if [[ -f "$STONKS_DIR/.env" ]]; then
    export $(grep -v '^#' "$STONKS_DIR/.env" | xargs)
fi

echo "" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') ══ Earnings refresh start ══" >> "$LOG"

"$VENV" earnings-refresh >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') ══ Earnings refresh done ══" >> "$LOG"
