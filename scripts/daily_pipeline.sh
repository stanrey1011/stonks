#!/usr/bin/env bash
# Fetch, clean, and analyze all tickers after market close.
# Runs at 20:30 UTC (10:30am HST) weekdays — data is ready for the morning alert.
# Crontab: 30 20 * * 1-5 /home/as/homelab/apps/stonks/scripts/daily_pipeline.sh

set -euo pipefail

STONKS_DIR="/home/as/homelab/apps/stonks"
VENV="$STONKS_DIR/venv/bin/stonks"
LOG="$STONKS_DIR/log/pipeline.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') — Starting pipeline" >> "$LOG"

"$VENV" pipeline all --interval 1d  >> "$LOG" 2>&1
"$VENV" pipeline all --interval 1wk >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Pipeline done" >> "$LOG"
