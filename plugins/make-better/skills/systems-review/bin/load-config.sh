#!/usr/bin/env bash
# Wrapper: runs load-config.py with whichever python is available.
# Usage: bash ${CLAUDE_SKILL_DIR}/bin/load-config.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "ERROR: python3 (or python) not found in PATH" >&2
  exit 1
fi
exec "$PY" "$DIR/load-config.py"
