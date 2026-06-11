# Phase 3 — Finish (sync base into task, local merge into base + push + full cleanup)

Runs **only** on an explicit user go-ahead ("done", "finish", "merge it", or the equivalent in the
user's language). Confirm once before merging. Read `<worktrees>/<task>/.feature.json` for the repos,
base branches, ports, PIDs, and PR links. Do every step for **all** involved repos.

**Strategy:** first bring the latest base into the task branch **inside the worktree, and resolve any
conflicts there — on the task branch itself**. That lands the integration in the **PR** (so it's
reviewable and CI runs on the exact code that will merge), and makes the final step trivial. Then
merge the now-up-to-date task branch into the main checkout's base branch **locally** and push.
Pushing the task commits into the base makes the host mark the PR **Merged** automatically — no
`gh pr merge` — and leaves your local base already updated. Do **not** squash/rebase: that rewrites
SHAs and the host would not detect the merge (the PR would show Closed, not Merged). We use `merge`
precisely to keep the SHAs intact.

Per repo: `WT="$ROOT/<worktrees>/<task>/<repo>"`, branch `task-<task>`, `BASE` = `.feature.json`
`.repos.<repo>.base` (the repo's `base_branch`). `ROOT` = the workspace root — anchor it as in
`workspace.md` (walk up to the `.claude/feature/config.json` marker), never `$(pwd)`.
`SCRIPTS="${CLAUDE_SKILL_DIR}/scripts"`.

## 1. Make sure the task branch is fully committed

```bash
git -C "$WT" status --porcelain   # must be empty
```

## 2. Sync the latest base into the task branch — resolve conflicts HERE (in the worktree)

This is where conflicts are handled: on the **task branch**, in its worktree, so the PR shows exactly
what will land and CI runs on it. Skip the merge if the task already contains the latest base.

```bash
git -C "$WT" fetch origin "$BASE"
if git -C "$WT" merge-base --is-ancestor "origin/$BASE" HEAD; then
  echo "task already up to date with $BASE — nothing to sync"
else
  git -C "$WT" merge --no-ff "origin/$BASE" -m "Merge $BASE into task-<task>"
fi
git -C "$WT" push                 # updates the PR; its head SHA is what we'll merge
```

On conflict git stops with a non-zero exit. Resolve the conflicted files **in `$WT`** (the task
worktree), then `git -C "$WT" add -A && git -C "$WT" commit --no-edit` and push. If you can't resolve
confidently, **ask the user** before committing — never guess a conflict resolution.

## 3. Wait for the PR's CI to go green

The whole reason we sync in the worktree is so CI validates the *integrated* code before it reaches the
base. Don't integrate on red.

```bash
PR=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['repos']['<repo>']['pr'] or '')" "$ROOT/<worktrees>/<task>/.feature.json")
[ -n "$PR" ] && gh pr checks "$PR" --watch   # wait for green; no-op/skip if the repo has no required checks
```

If checks fail, fix on the task branch (back to step 2) — do **not** proceed to integration.

## 4. Prepare the main checkout (the integration point for BASE)

`$ROOT/<repo>` is where `BASE` lives. It MUST be on `BASE` and clean — otherwise STOP and tell the
user (don't auto-stash someone else's work).

```bash
test "$(git -C "$ROOT/<repo>" rev-parse --abbrev-ref HEAD)" = "$BASE"   # else STOP
test -z "$(git -C "$ROOT/<repo>" status --porcelain)"                   # else STOP
git -C "$ROOT/<repo>" pull --ff-only origin "$BASE"                     # latest base
```

## 5. Merge the task branch into BASE — now conflict-free

Because the task branch already contains the latest `BASE` (step 2), this merge carries no conflicts.

```bash
git -C "$ROOT/<repo>" merge --no-ff "task-<task>" -m "Merge task-<task> into $BASE"
```

If git *does* report a conflict here, `BASE` moved again between step 2 and now — go back to **step 2**
(re-sync the task branch, push, wait for CI), then retry. Never guess a resolution on the `BASE` side.

## 6. Push — this *is* the PR merge

```bash
git -C "$ROOT/<repo>" push origin "$BASE"
```

Verify the PR flipped (the worktree/branch still exists at this point):

```bash
[ -n "$PR" ] && gh pr view "$PR" --json state -q .state   # expect: MERGED
```

If it still shows OPEN, the host didn't see the head SHA in `BASE` — confirm step 2 pushed and the
worktree HEAD == the PR head before continuing.

## 7. Stop the dev servers

**Skip in `--lite` mode.** Servers were started detached via `serve.py`, so `dev_pid` is also the
process-group id — kill the whole group to catch worker children:

```bash
kill -- -<dev_pid>                                       # from .feature.json, per repo (negative = the group)
kill -0 <dev_pid> 2>/dev/null && kill -9 -- -<dev_pid>   # SIGKILL any straggler
```

## 8. Remove the worktree and delete the branches

```bash
git -C "$ROOT/<repo>" worktree remove --force "$WT"
git -C "$ROOT/<repo>" branch -d "task-<task>"            # -d is safe (already merged); use -D only if it refuses
git -C "$ROOT/<repo>" push origin --delete "task-<task>" # tolerate "remote ref does not exist"
git -C "$ROOT/<repo>" worktree prune
```

## 9. Free the ports, proxy, and workspace folder

```bash
python3 "$SCRIPTS/ports.py" --root "$ROOT" free <task>            # full mode only; no-op otherwise
python3 "$SCRIPTS/caddyfile.py" --root "$ROOT" --reload           # drop the task's hosts
rm -rf "$ROOT/<worktrees>/<task>"   # leftover .feature.json / empty repo dirs
```

## 10. Report

Tell the user (in their language): which PR(s) are now **Merged** (with links), that the local base was
updated & pushed, that worktrees/branches/ports/proxy were cleaned up, and any follow-up (deploy, QA,
related tickets).

## 11. Reflect — propose new `considerations` from this session

After reporting, look back over **this session's own history** (what was built, what got reworked,
what review feedback / bugs / "oh, also fix X" came up mid-task) and compare it against the current
`considerations` list in `.claude/feature/config.json`. The goal is a self-improving checklist: a
class of issue that bit *this* task — and isn't yet covered — is exactly what should be caught
automatically next time.

- If you spot a **recurring, cross-cutting** dimension that's missing (e.g. the user kept asking
  "what about mobile?", a bug turned out to be RTL-only, an empty/error state was forgotten, a
  migration was nearly missed) → propose adding it. Show the concrete entry you'd append
  (`name`, `when`, `check`, optional `repos`) and *why this session suggests it*.
- Be conservative: propose only genuinely **reusable** dimensions, not one-off task details. One or
  two strong candidates beat a long speculative list. If nothing qualifies, say so and add nothing.
- **Only on the user's approval**, append the approved entries to the `considerations` array in
  `.claude/feature/config.json` (read it, add, write it back — don't touch anything else). From the
  next feature on, the iteration contract (§2b) will validate them automatically.

This step never blocks finish — the merge/cleanup above is already complete. It's a quick "should we
teach the checklist something?" at the very end.
