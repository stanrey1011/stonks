#!/bin/bash

PATTERN_DIR="../stonkslib/patterns"
INDICATOR_DIR="../stonkslib/indicators"
UTILS_DIR="../stonkslib/utils"
DATA_DIR="../data/ticker_data"
DEV_DIR="../dev"
DRY_RUN=false
TEST_TICKER="AAPL"
TEST_INTERVAL="1d"

if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "💡 DRY RUN ENABLED – no changes will be made"
fi

echo "🧠 Running sanity check for stonkslib..."

echo "🔍 Scanning for lingering 'detect_' references..."
if grep -r --exclude-dir="__pycache__" "detect_" "$PATTERN_DIR" | grep -q .; then
    grep -r --exclude-dir="__pycache__" "detect_" "$PATTERN_DIR"
    echo "❌ Found lingering 'detect_' function references."
else
    echo "✅ No stale 'detect_' functions found."
fi

echo "🔍 Checking each pattern module has a 'find_' function..."
for file in "$PATTERN_DIR"/*.py; do
    filename=$(basename "$file")

    if grep -q '@pattern_module: false' "$file"; then
        echo "🟡 Skipping $file (marked as non-pattern module)"
        continue
    fi

    if grep -q 'def find_' "$file"; then
        echo "✅ $file has a find_ function"
    else
        echo "⚠️  $file has NO find_ function"
    fi
done

echo "🧪 Testing stonks CLI: stonks --help"
if $DRY_RUN; then
    echo "💡 Skipping CLI load in dry-run mode"
else
    if stonks --help &>/dev/null; then
        echo "✅ CLI loads successfully"
    else
        echo "❌ CLI failed to load — check import errors"
    fi
fi

echo "📁 Checking required data files exist for $TEST_TICKER ($TEST_INTERVAL)..."
RAW_FILE="$DATA_DIR/raw/$TEST_INTERVAL/$TEST_TICKER.csv"
CLEAN_FILE="$DATA_DIR/clean/$TEST_INTERVAL/$TEST_TICKER.csv"

[[ -f "$RAW_FILE" ]] && echo "✅ Raw file exists: $RAW_FILE" || echo "❌ Missing raw file: $RAW_FILE"
[[ -f "$CLEAN_FILE" ]] && echo "✅ Clean file exists: $CLEAN_FILE" || echo "❌ Missing clean file: $CLEAN_FILE"

if ! $DRY_RUN; then
    echo "📊 Running indicator tests..."
    for mod in bollinger obv macd; do
        echo "🔧 Testing $mod.py..."
        python3 -c "from stonkslib.indicators import $mod; print('✅ $mod imported')"
    done

    echo "📈 Testing pattern modules..."
    for mod in doubles triangles wedges; do
        echo "🔧 Testing $mod.py..."
        python3 -c "from stonkslib.patterns import $mod; print('✅ $mod imported')"
    done

    echo "🧹 Testing clean/load helpers..."
    python3 -c "from stonkslib.utils import clean_td, load_td; print('✅ clean_td/load_td imported')"
else
    echo "💡 Skipping indicator and pattern tests in dry-run mode"
fi

echo "✅ Sanity check complete."
