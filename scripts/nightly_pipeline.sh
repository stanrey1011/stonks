#!/usr/bin/env bash
# Nightly data pipeline — runs after US market close.
# Fetches fresh OHLCV data, cleans, and runs signal analysis for all tickers.
#
# Scheduled via stonks-pipeline.timer (Mon-Fri 20:00 UTC / 4pm ET).
# The alert scan (stonks-alert.timer) runs at 20:30 UTC and depends on this finishing first.

set -euo pipefail

STONKS_DIR="/home/as/homelab/apps/stonks"
VENV="$STONKS_DIR/venv/bin/stonks"
LOG="$STONKS_DIR/log/pipeline.log"

mkdir -p "$STONKS_DIR/log"

if [[ -f "$STONKS_DIR/.env" ]]; then
    export $(grep -v '^#' "$STONKS_DIR/.env" | xargs)
fi

echo "" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') ══ Pipeline start ══" >> "$LOG"

"$VENV" pipeline all --interval 1d  >> "$LOG" 2>&1
"$VENV" pipeline all --interval 1wk >> "$LOG" 2>&1

# News sentiment: top up the archive (last 30 days) and score any new ticker-days
# with the local LLM. Supplementary — never let it abort the core pipeline.
# 30d costs the same as a shorter window (one Finnhub call/ticker, dedup by id) and
# survives missed runs + late-attributed articles.
"$VENV" news-backfill all --days 30 >> "$LOG" 2>&1 || echo "$(date '+%Y-%m-%d %H:%M:%S') [!] news-backfill failed" >> "$LOG"
"$VENV" sentiment-score all         >> "$LOG" 2>&1 || echo "$(date '+%Y-%m-%d %H:%M:%S') [!] sentiment-score failed" >> "$LOG"

echo "$(date '+%Y-%m-%d %H:%M:%S') ══ Pipeline done ══" >> "$LOG"
