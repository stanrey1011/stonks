DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/sh

TARGET="../stonkslib/patterns/triangles.py"

if [ -f "$TARGET" ]; then
if $DRY_RUN; then
  echo "🔍 Would run:     echo "[~] Patching alias in $TARGET ...""
else
      echo "[~] Patching alias in $TARGET ..."
fi

    # Remove any early incorrect alias
if $DRY_RUN; then
  echo "🔍 Would run:     sed -i '/find_triangle_patterns *=/d' "$TARGET""
else
      sed -i '/find_triangle_patterns *=/d' "$TARGET"
fi

    # Append correct alias to end of file
if $DRY_RUN; then
  echo "🔍 Would run:     echo "" >> "$TARGET""
else
      echo "" >> "$TARGET"
fi
if $DRY_RUN; then
  echo "🔍 Would run:     echo "find_triangle_patterns = detect_triangle_patterns" >> "$TARGET""
else
      echo "find_triangle_patterns = detect_triangle_patterns" >> "$TARGET"
fi

if $DRY_RUN; then
  echo "🔍 Would run:     echo "[✔] Alias added at the bottom: find_triangle_patterns = detect_triangle_patterns""
else
      echo "[✔] Alias added at the bottom: find_triangle_patterns = detect_triangle_patterns"
fi
else
if $DRY_RUN; then
  echo "🔍 Would run:     echo "[✘] File not found: $TARGET""
else
      echo "[✘] File not found: $TARGET"
fi
fi
