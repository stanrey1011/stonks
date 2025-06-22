DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/bash

ZIP_PATH="stonkslib_final_cleaned.zip"
EXTRACT_DIR="../tmp_stonkslib_clean"
TARGET_DIR="../stonkslib"

# Cleanup any old extraction
if $DRY_RUN; then
  echo "🔍 Would run: rm -rf "$EXTRACT_DIR""
else
  rm -rf "$EXTRACT_DIR"
fi

# Extract
if $DRY_RUN; then
  echo "🔍 Would run: unzip -q "$ZIP_PATH" -d "$EXTRACT_DIR""
else
  unzip -q "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

# Try nested path
NESTED_PATH="$EXTRACT_DIR/stonks/stonkslib"

if [ ! -d "$NESTED_PATH" ]; then
if $DRY_RUN; then
  echo "🔍 Would run:     echo "[✘] stonkslib folder not found in the zip.""
else
      echo "[✘] stonkslib folder not found in the zip."
fi
    exit 1
fi

# Replace old stonkslib
if $DRY_RUN; then
  echo "🔍 Would run: rm -rf "$TARGET_DIR""
else
  rm -rf "$TARGET_DIR"
fi
if $DRY_RUN; then
  echo "🔍 Would run: mv "$NESTED_PATH" "$TARGET_DIR""
else
  mv "$NESTED_PATH" "$TARGET_DIR"
fi

# Cleanup
if $DRY_RUN; then
  echo "🔍 Would run: rm -rf "$EXTRACT_DIR""
else
  rm -rf "$EXTRACT_DIR"
fi

if $DRY_RUN; then
  echo "🔍 Would run: echo "[✔] stonkslib folder replaced successfully.""
else
  echo "[✔] stonkslib folder replaced successfully."
fi
