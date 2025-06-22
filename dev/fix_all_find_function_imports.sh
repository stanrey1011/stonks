DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/bash

if $DRY_RUN; then
  echo "🔍 Would run: echo "🔧 Scanning for outdated find_ function imports and replacing with standardized versions...""
else
  echo "🔧 Scanning for outdated find_ function imports and replacing with standardized versions..."
fi

# Mapping of old function names to standardized new names
declare -A FIXES=(
  ["find_head_shoulders"]="find_head_shoulders_patterns"
  ["find_triangle"]="find_triangle_patterns"
  ["find_wedge"]="find_wedge_patterns"
  ["find_double"]="find_double_patterns"
)

# Directory to search
TARGET_DIR="../stonkslib"

# Find all .py files (excluding __pycache__)
FILES=$(find "$TARGET_DIR" -type f -name "*.py" ! -path "*/__pycache__/*")

for file in $FILES; do
  for OLD in "${!FIXES[@]}"; do
    NEW=${FIXES[$OLD]}
    if grep -q "\b$OLD\b" "$file"; then
if $DRY_RUN; then
  echo "🔍 Would run:       sed -i "s/\b$OLD\b/$NEW/g" "$file""
else
        sed -i "s/\b$OLD\b/$NEW/g" "$file"
fi
if $DRY_RUN; then
  echo "🔍 Would run:       echo "✅ Replaced $OLD → $NEW in $file""
else
        echo "✅ Replaced $OLD → $NEW in $file"
fi
    fi
  done
done

if $DRY_RUN; then
  echo "🔍 Would run: echo "✨ All outdated function names replaced!""
else
  echo "✨ All outdated function names replaced!"
fi
