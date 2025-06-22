DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "💡 Dry run enabled — no changes will be made."
fi

#!/bin/bash

set -e

if $DRY_RUN; then
  echo "🔍 Would run: echo "[⟳] Updating function names in pattern detectors...""
else
  echo "[⟳] Updating function names in pattern detectors..."
fi

# Set the relative path from dev/
PATTERN_DIR="../stonkslib/patterns"

# 1. Rename function definitions
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/^def detect_double_patterns/def find_double_patterns/' "$PATTERN_DIR/doubles.py""
else
  sed -i 's/^def detect_double_patterns/def find_double_patterns/' "$PATTERN_DIR/doubles.py"
fi
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/^def detect_triangle_patterns/def find_triangle_patterns/' "$PATTERN_DIR/triangles.py""
else
  sed -i 's/^def detect_triangle_patterns/def find_triangle_patterns/' "$PATTERN_DIR/triangles.py"
fi
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/^def detect_head_shoulders/def find_head_shoulders/' "$PATTERN_DIR/head_shoulders.py""
else
  sed -i 's/^def detect_head_shoulders/def find_head_shoulders/' "$PATTERN_DIR/head_shoulders.py"
fi
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/^def detect_wedge_patterns/def find_wedge_patterns/' "$PATTERN_DIR/wedges.py""
else
  sed -i 's/^def detect_wedge_patterns/def find_wedge_patterns/' "$PATTERN_DIR/wedges.py"
fi

# 2. Update imports in historical_pattern_analysis.py
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/from stonkslib.patterns.doubles import .*/from stonkslib.patterns.doubles import find_double_patterns/' "$PATTERN_DIR/historical_pattern_analysis.py""
else
  sed -i 's/from stonkslib.patterns.doubles import .*/from stonkslib.patterns.doubles import find_double_patterns/' "$PATTERN_DIR/historical_pattern_analysis.py"
fi
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/from stonkslib.patterns.triangles import .*/from stonkslib.patterns.triangles import find_triangle_patterns/' "$PATTERN_DIR/historical_pattern_analysis.py""
else
  sed -i 's/from stonkslib.patterns.triangles import .*/from stonkslib.patterns.triangles import find_triangle_patterns/' "$PATTERN_DIR/historical_pattern_analysis.py"
fi
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/from stonkslib.patterns.head_shoulders import .*/from stonkslib.patterns.head_shoulders import find_head_shoulders/' "$PATTERN_DIR/historical_pattern_analysis.py""
else
  sed -i 's/from stonkslib.patterns.head_shoulders import .*/from stonkslib.patterns.head_shoulders import find_head_shoulders/' "$PATTERN_DIR/historical_pattern_analysis.py"
fi
if $DRY_RUN; then
  echo "🔍 Would run: sed -i 's/from stonkslib.patterns.wedges import .*/from stonkslib.patterns.wedges import find_wedge_patterns/' "$PATTERN_DIR/historical_pattern_analysis.py""
else
  sed -i 's/from stonkslib.patterns.wedges import .*/from stonkslib.patterns.wedges import find_wedge_patterns/' "$PATTERN_DIR/historical_pattern_analysis.py"
fi

if $DRY_RUN; then
  echo "🔍 Would run: echo "[✔] Function names and imports updated successfully.""
else
  echo "[✔] Function names and imports updated successfully."
fi
