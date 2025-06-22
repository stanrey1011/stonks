DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/bash

if $DRY_RUN; then
  echo "🔍 Would run: echo "🔍 Updating imports in pattern modules...""
else
  echo "🔍 Updating imports in pattern modules..."
fi

PATTERNS_DIR="../stonkslib/patterns"

# Map of old -> new function names (add to this as needed)
declare -A function_map=(
  ["detect_double_patterns"]="find_double_patterns"
  ["detect_head_shoulders_patterns"]="find_head_shoulders_patterns"
  ["detect_triangle_patterns"]="find_triangle_patterns"
  ["detect_wedge_patterns"]="find_wedge_patterns"
)

for file in "$PATTERNS_DIR"/*.py; do
  for old in "${!function_map[@]}"; do
    new="${function_map[$old]}"
    grep -q "$old" "$file" && {
if $DRY_RUN; then
  echo "🔍 Would run:       sed -i "s/\b$old\b/$new/g" "$file""
else
        sed -i "s/\b$old\b/$new/g" "$file"
fi
if $DRY_RUN; then
  echo "🔍 Would run:       echo "🔧 Replaced $old with $new in $(basename "$file")""
else
        echo "🔧 Replaced $old with $new in $(basename "$file")"
fi
    }
  done
done

if $DRY_RUN; then
  echo "🔍 Would run: echo "✅ Import cleanup complete.""
else
  echo "✅ Import cleanup complete."
fi
