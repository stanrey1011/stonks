DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/sh

PATTERNS_DIR="../stonkslib/patterns"

for file in "$PATTERNS_DIR"/*.py; do
  [ ! -f "$file" ] && continue
  case "$file" in *__init__.py) continue ;; esac

  # Extract the first detect_ function name found anywhere
  detect_fn=$(grep -Eo 'def[[:space:]]+detect_[a-zA-Z0-9_]+' "$file" | head -n1 | awk '{print $2}')

  if [ -n "$detect_fn" ]; then
    find_fn=$(echo "$detect_fn" | sed 's/detect_/find_/')

    # Check if alias already exists
    if grep -qE "${find_fn}[[:space:]]*=" "$file"; then
if $DRY_RUN; then
  echo "🔍 Would run:       echo "✅ Alias already exists in $file: $find_fn""
else
        echo "✅ Alias already exists in $file: $find_fn"
fi
    else
if $DRY_RUN; then
  echo "🔍 Would run:       echo "🛠  Adding alias to $file: $find_fn = $detect_fn""
else
        echo "🛠  Adding alias to $file: $find_fn = $detect_fn"
fi
      printf "\n# === Alias for uniform import ===\n%s = %s\n" "$find_fn" "$detect_fn" >> "$file"
    fi
  else
if $DRY_RUN; then
  echo "🔍 Would run:     echo "⚠️  No detect_ function found in $file""
else
      echo "⚠️  No detect_ function found in $file"
fi
  fi
done
