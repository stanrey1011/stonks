#!/bin/bash
set -e

DEV_DIR="./"
HEADER='DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi
'

echo "🔧 Adding dry-run support to all .sh scripts in: $DEV_DIR"

for script in "$DEV_DIR"*.sh; do
  [[ -f "$script" ]] || continue
  if grep -q "DRY_RUN=" "$script"; then
    echo "✅ Skipping (already supports dry-run): $script"
    continue
  fi

  echo "🔨 Modifying: $script"

  tmpfile="$(mktemp)"
  echo "$HEADER" > "$tmpfile"

  # Add dry-run wrapper for common commands
  awk '
  BEGIN { dry=0 }
  {
    if ($1 ~ /^(sed|rm|cp|mv|mkdir|rmdir|touch|echo|unzip)/ && $0 !~ /DRY_RUN/) {
      print "if $DRY_RUN; then"
      print "  echo \"🔍 Would run: " $0 "\""
      print "else"
      print "  " $0
      print "fi"
    } else {
      print $0
    }
  }' "$script" >> "$tmpfile"

  mv "$tmpfile" "$script"
  chmod +x "$script"
done

echo "✅ Dry-run support added where missing."
