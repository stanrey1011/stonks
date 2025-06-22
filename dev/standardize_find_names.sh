DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/bash

PATTERNS_DIR="../stonkslib/patterns"

if $DRY_RUN; then
  echo "🔍 Would run: echo "📦 Standardizing function names to use 'find_' in $PATTERNS_DIR""
else
  echo "📦 Standardizing function names to use 'find_' in $PATTERNS_DIR"
fi

for file in "$PATTERNS_DIR"/*.py; do
if $DRY_RUN; then
  echo "🔍 Would run:   echo "🔧 Processing: $file""
else
    echo "🔧 Processing: $file"
fi

  # Get the original function name that starts with 'def detect_...'
  DETECT_LINE=$(grep -Eo '^def[[:space:]]+detect_[a-zA-Z0-9_]+' "$file" | head -n1)
  if [ -z "$DETECT_LINE" ]; then
if $DRY_RUN; then
  echo "🔍 Would run:     echo "⚠️  No 'detect_' function found in $file""
else
      echo "⚠️  No 'detect_' function found in $file"
fi
    continue
  fi

  DETECT_FUNC=$(echo "$DETECT_LINE" | awk '{print $2}')
  FIND_FUNC=$(echo "$DETECT_FUNC" | sed 's/^detect_/find_/')

  # Rename the function definition
if $DRY_RUN; then
  echo "🔍 Would run:   sed -i "s/def $DETECT_FUNC/def $FIND_FUNC/" "$file""
else
    sed -i "s/def $DETECT_FUNC/def $FIND_FUNC/" "$file"
fi

  # Replace all uses of the detect_ function internally
if $DRY_RUN; then
  echo "🔍 Would run:   sed -i "s/\b$DETECT_FUNC\b/$FIND_FUNC/g" "$file""
else
    sed -i "s/\b$DETECT_FUNC\b/$FIND_FUNC/g" "$file"
fi

  # Remove alias lines like: find_x = detect_x
if $DRY_RUN; then
  echo "🔍 Would run:   sed -i "/^$FIND_FUNC[[:space:]]*=[[:space:]]*$DETECT_FUNC/d" "$file""
else
    sed -i "/^$FIND_FUNC[[:space:]]*=[[:space:]]*$DETECT_FUNC/d" "$file"
fi

if $DRY_RUN; then
  echo "🔍 Would run:   echo "✅ Renamed '$DETECT_FUNC' → '$FIND_FUNC' in $(basename "$file")""
else
    echo "✅ Renamed '$DETECT_FUNC' → '$FIND_FUNC' in $(basename "$file")"
fi
done

if $DRY_RUN; then
  echo "🔍 Would run: echo "✨ All pattern detection functions standardized.""
else
  echo "✨ All pattern detection functions standardized."
fi
