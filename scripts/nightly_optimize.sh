#!/usr/bin/env bash
# Two-phase nightly strategy optimization — runs while you sleep.
#
# Phase 1 (fast exploration): all strategies × all tickers, 3 iterations, qwen2.5:7b
# Phase 2 (refinement):       same, 3 iterations, qwen2.5:32b, warm-starts from phase 1 results
#
# Scheduled via systemd timer: stonks-optimize.timer (Mon-Fri 10:00 UTC / midnight HST)
# Runs after the pipeline (20:30 UTC) so data is fresh.
#
# Total runtime estimate: ~20-30 min depending on model load and ticker count.

set -euo pipefail

STONKS_DIR="/home/as/stonks"
VENV="$STONKS_DIR/venv/bin/stonks"
LOG="$STONKS_DIR/log/optimize.log"

mkdir -p "$STONKS_DIR/log"

if [[ -f "$STONKS_DIR/.env" ]]; then
    export $(grep -v '^#' "$STONKS_DIR/.env" | xargs)
fi

echo "" >> "$LOG"
echo "$(date '+%Y-%m-%d %H:%M:%S') ══ Nightly optimize start ══" >> "$LOG"

# ── Phase 1: fast exploration with 7b ────────────────────────────────────────
echo "$(date '+%Y-%m-%d %H:%M:%S') — Phase 1: 7b exploration (3 iterations, 1d)" >> "$LOG"
"$VENV" optimize --all-strategies --all-tickers \
    --interval 1d --iterations 3 --model qwen2.5:7b \
    >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Phase 1: 7b exploration (3 iterations, 1wk)" >> "$LOG"
"$VENV" optimize --all-strategies --all-tickers \
    --interval 1wk --iterations 3 --model qwen2.5:7b \
    >> "$LOG" 2>&1

# ── Phase 2: refinement with 32b (warm-starts from phase 1 results) ──────────
echo "$(date '+%Y-%m-%d %H:%M:%S') — Phase 2: 32b refinement (3 iterations, 1d)" >> "$LOG"
"$VENV" optimize --all-strategies --all-tickers \
    --interval 1d --iterations 3 --model qwen2.5:32b --warm-start \
    >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') — Phase 2: 32b refinement (3 iterations, 1wk)" >> "$LOG"
"$VENV" optimize --all-strategies --all-tickers \
    --interval 1wk --iterations 3 --model qwen2.5:32b --warm-start \
    >> "$LOG" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') ══ Nightly optimize done ══" >> "$LOG"

# ── Optional Discord notification ─────────────────────────────────────────────
if [[ -n "${STONKS_DISCORD_WEBHOOK:-}" ]]; then
    curl -s -X POST "$STONKS_DISCORD_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"content\": \"✅ **Nightly optimize complete** — strategies updated for 1d + 1wk. $(date '+%Y-%m-%d %H:%M UTC')\"}" \
        >> "$LOG" 2>&1
fi
