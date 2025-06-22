DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/sh

TARGET="../stonkslib/patterns/doubles.py"

if [ -f "$TARGET" ]; then
if $DRY_RUN; then
  echo "🔍 Would run:     echo "[~] Patching alias in $TARGET ...""
else
      echo "[~] Patching alias in $TARGET ..."
fi
    
    # Replace incorrect alias if it exists
if $DRY_RUN; then
  echo "🔍 Would run:     sed -i 's/^find_double_top_bottom *= *detect_double_patterns/find_double_top_bottom = find_double_patterns/' "$TARGET""
else
      sed -i 's/^find_double_top_bottom *= *detect_double_patterns/find_double_top_bottom = find_double_patterns/' "$TARGET"
fi
    
if $DRY_RUN; then
  echo "🔍 Would run:     echo "[✔] Alias updated to: find_double_top_bottom = find_double_patterns""
else
      echo "[✔] Alias updated to: find_double_top_bottom = find_double_patterns"
fi
else
if $DRY_RUN; then
  echo "🔍 Would run:     echo "[✘] File not found: $TARGET""
else
      echo "[✘] File not found: $TARGET"
fi
fi
