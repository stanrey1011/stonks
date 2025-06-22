#!/bin/bash

PATTERN_DIR="../stonkslib/patterns"
DRY_RUN=false

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

echo "🧪 Trying CLI import test: stonks --help"
if $DRY_RUN; then
    echo "💡 Skipping CLI load in dry-run mode"
else
    if stonks --help &>/dev/null; then
        echo "✅ CLI loads successfully"
    else
        echo "❌ CLI failed to load — check import errors"
    fi
fi

echo "🧼 Sanity check complete."
