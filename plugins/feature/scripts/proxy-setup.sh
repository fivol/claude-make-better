#!/usr/bin/env bash
# One-time setup for pretty *.localhost URLs (run by the user, needs sudo once).
# After this, the `feature` skill only runs `caddy reload` per task — no sudo.
#
# Run this from inside your workspace (the dir tree containing
# .claude/feature/config.json). The skill's scripts are alongside this file.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Workspace root = nearest ancestor of $PWD holding .claude/feature/config.json
# (fallback: $PWD). --root passed here is just an optional explicit override.
ROOT="${1:-}"
if [ -z "$ROOT" ]; then
  d="$PWD"
  while [ "$d" != / ] && [ ! -f "$d/.claude/feature/config.json" ]; do d="$(dirname "$d")"; done
  ROOT="$d"
  [ "$ROOT" = / ] && ROOT="$PWD"
fi
echo "workspace root: $ROOT"

BREW_PREFIX="$(brew --prefix)"
BREW_CADDYFILE="$BREW_PREFIX/etc/Caddyfile"

# 1. Install Caddy if missing.
if ! command -v caddy >/dev/null 2>&1; then
  echo "Installing caddy…"; brew install caddy
fi

# 2. Generate the Caddyfile (even if empty / no tasks yet) and learn its path.
WT_CADDYFILE="$(python3 "$SCRIPT_DIR/caddyfile.py" --root "$ROOT" | sed -n 's/^wrote //p')"
if [ -z "$WT_CADDYFILE" ]; then
  echo "ERROR: caddyfile.py did not report a path" >&2; exit 1
fi
echo "generated: $WT_CADDYFILE"

# 3. Make the brew Caddyfile import ours (idempotent).
touch "$BREW_CADDYFILE"
IMPORT_LINE="import $WT_CADDYFILE"
if ! grep -qxF "$IMPORT_LINE" "$BREW_CADDYFILE"; then
  printf '\n%s\n' "$IMPORT_LINE" >> "$BREW_CADDYFILE"
  echo "added import line to $BREW_CADDYFILE"
fi

# 4. Run Caddy as a root launchd service so it can bind :80.
echo "Starting caddy on :80 (sudo)…"
sudo brew services restart caddy

echo
echo "Done. Checks:"
lsof -nP -iTCP:80   -sTCP:LISTEN | grep -i caddy || echo "  WARNING: nothing listening on :80"
curl -s localhost:2019/config/ >/dev/null && echo "  admin API :2019 OK (caddy reload will work without sudo)" \
  || echo "  WARNING: admin API :2019 not reachable"
echo
echo "Open a workspace URL in Chrome, e.g. http://<task>.localhost/"
