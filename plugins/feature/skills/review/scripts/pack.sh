#!/usr/bin/env bash
# Build one repo's review pack for the `feature:review` gate.
#
# The pack is the ENTIRE scope in one file — the committed range, the uncommitted
# diff and every untracked file — so the finders read a path instead of each
# rebuilding the same diff with their own `git` calls. Getting that range right
# by hand is the step that silently narrows a review, so it lives here instead.
#
# Usage:
#   pack.sh --wt DIR --repo NAME --scope working|branch --base BRANCH --out DIR
#
# Writes <out>/<repo>.diff, .files, .log, .head and prints one summary line:
#   <repo>: <n> changed lines · <n> files · <n> commits · head <sha> · range <range>

set -uo pipefail

WT= ; REPO= ; SCOPE=working ; BASE= ; OUT=

while [ $# -gt 0 ]; do
  case "$1" in
    --wt)    WT=${2-} ; shift 2 ;;
    --repo)  REPO=${2-} ; shift 2 ;;
    --scope) SCOPE=${2-} ; shift 2 ;;
    --base)  BASE=${2-} ; shift 2 ;;
    --out)   OUT=${2-} ; shift 2 ;;
    -h|--help) sed -n '2,13p' "$0" ; exit 0 ;;
    *) echo "pack.sh: unknown argument: $1" >&2 ; exit 2 ;;
  esac
done

[ -n "$WT" ]   || { echo "pack.sh: --wt is required" >&2 ; exit 2 ; }
[ -n "$REPO" ] || { echo "pack.sh: --repo is required" >&2 ; exit 2 ; }
[ -n "$BASE" ] || { echo "pack.sh: --base is required" >&2 ; exit 2 ; }
[ -n "$OUT" ]  || { echo "pack.sh: --out is required" >&2 ; exit 2 ; }

git -C "$WT" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "pack.sh: $WT is not a git checkout" >&2 ; exit 2 ; }

mkdir -p "$OUT" || exit 2

# --- resolve the committed range ------------------------------------------------
# working: what is not yet in the PR — the commits past the upstream, or the whole
#          branch when it has never been pushed.
# branch:  the whole change as it will land, against a freshly fetched base.
RANGE=""
if [ "$SCOPE" = "branch" ]; then
  git -C "$WT" fetch -q origin "$BASE" 2>/dev/null
  git -C "$WT" rev-parse --verify -q "origin/$BASE" >/dev/null 2>&1 \
    && RANGE="origin/$BASE...HEAD"
else
  if git -C "$WT" rev-parse --verify -q '@{upstream}' >/dev/null 2>&1; then
    RANGE='@{upstream}..HEAD'
  elif git -C "$WT" rev-parse --verify -q "origin/$BASE" >/dev/null 2>&1; then
    RANGE="origin/$BASE...HEAD"      # never pushed ⇒ the whole branch is unreviewed
  fi
fi

DIFF="$OUT/$REPO.diff"
FILES="$OUT/$REPO.files"
LOG="$OUT/$REPO.log"

# --- the diff: committed range + uncommitted + every untracked file --------------
{
  [ -n "$RANGE" ] && git -C "$WT" diff "$RANGE"
  git -C "$WT" diff HEAD
  git -C "$WT" ls-files --others --exclude-standard -z | while IFS= read -r -d '' f; do
    # A new file is an all-added hunk, and it is exactly what `git diff` misses.
    # Binaries are named but not inlined — nobody reviews them line by line.
    if grep -Iq . "$WT/$f" 2>/dev/null; then
      printf '\n--- NEW FILE: %s ---\n' "$f"
      cat "$WT/$f"
    else
      printf '\n--- NEW BINARY FILE (not inlined): %s ---\n' "$f"
    fi
  done
} > "$DIFF" 2>/dev/null

# --- the inventory --------------------------------------------------------------
{
  [ -n "$RANGE" ] && git -C "$WT" diff --name-status "$RANGE"
  git -C "$WT" diff --name-status HEAD
  git -C "$WT" ls-files --others --exclude-standard | sed 's/^/A	/'
} 2>/dev/null | sort -u -k2 > "$FILES"

{
  [ -n "$RANGE" ] && git -C "$WT" log --oneline "${RANGE/.../..}"
} 2>/dev/null > "$LOG"

git -C "$WT" rev-parse HEAD > "$OUT/$REPO.head" 2>/dev/null

# --- summary --------------------------------------------------------------------
LINES=$(awk '/^\+\+\+ /||/^--- /{next} /^[+-]/{n++} END{print n+0}' "$DIFF" 2>/dev/null)
NFILES=$(awk 'END{print NR+0}' "$FILES" 2>/dev/null)
NCOMMITS=$(awk 'END{print NR+0}' "$LOG" 2>/dev/null)
HEAD=$(cut -c1-8 < "$OUT/$REPO.head" 2>/dev/null)
LINES=${LINES:-0} ; NFILES=${NFILES:-0} ; NCOMMITS=${NCOMMITS:-0}

printf '%s: %s changed lines · %s files · %s commits · head %s · range %s\n' \
       "$REPO" "$LINES" "$NFILES" "$NCOMMITS" "${HEAD:-?}" "${RANGE:-<uncommitted only>}"

[ "$LINES" -gt 0 ] || echo "$REPO: EMPTY — nothing in scope for this repo" >&2
