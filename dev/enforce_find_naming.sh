DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/bash

PATTERNS_DIR="../stonkslib/patterns"

if $DRY_RUN; then
  echo "🔍 Would run: echo "📦 Enforcing standardized 'find_' naming in $PATTERNS_DIR""
else
  echo "📦 Enforcing standardized 'find_' naming in $PATTERNS_DIR"
fi

for file in "$PATTERNS_DIR"/*.py; do
if $DRY_RUN; then
  echo "🔍 Would run:   echo "🔧 Processing: $file""
else
    echo "🔧 Processing: $file"
fi

  # Find all functions starting with 'find_'
  FIND_FUNCTIONS=$(grep -Eo '^def[[:space:]]+find_[a-zA-Z0-9_]+' "$file" | awk '{print $2}')

  if [ -z "$FIND_FUNCTIONS" ]; then
if $DRY_RUN; then
  echo "🔍 Would run:     echo "⚠️  No 'find_' functions found in $file""
else
      echo "⚠️  No 'find_' functions found in $file"
fi
    continue
  fi

  for func in $FIND_FUNCTIONS; do
    # Replace any lingering usage of detect_ function names
    DETECT_NAME=$(echo "$func" | sed 's/^find_/detect_/')
if $DRY_RUN; then
  echo "🔍 Would run:     sed -i "s/\b$DETECT_NAME\b/$func/g" "$file""
else
      sed -i "s/\b$DETECT_NAME\b/$func/g" "$file"
fi

    # Remove alias lines
if $DRY_RUN; then
  echo "🔍 Would run:     sed -i "/^$func[[:space:]]*=[[:space:]]*$DETECT_NAME/d" "$file""
else
      sed -i "/^$func[[:space:]]*=[[:space:]]*$DETECT_NAME/d" "$file"
fi

if $DRY_RUN; then
  echo "🔍 Would run:     echo "✅ Ensured use of '$func' in $(basename "$file")""
else
      echo "✅ Ensured use of '$func' in $(basename "$file")"
fi
  done
done

if $DRY_RUN; then
  echo "🔍 Would run: echo "✨ All 'find_' pattern functions cleaned and enforced.""
else
  echo "✨ All 'find_' pattern functions cleaned and enforced."
fi
