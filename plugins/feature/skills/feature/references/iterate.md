# Phase 2 — Iteration

Every prompt/edit once the workspace exists. The actual per-change contract now lives in the
**`iteration` skill** (the single source of truth); Phase 2 just wraps it with one feature-specific
step.

`ROOT` = the workspace root (walk up to the `.claude/feature/config.json` marker, never `$(pwd)`).
`SCRIPTS="${CLAUDE_SKILL_DIR}/scripts"`.

## 0. Reap stale workspaces first (feature-only)

Before touching anything, prune finished/abandoned workspaces so dev servers and worktrees don't pile
up. The reaper is cheap and self-throttling — run it every turn:

```bash
python3 "$SCRIPTS/reap.py" --root "$ROOT"
```

It clears dead PIDs, keeps at most `max_live_servers` (config; default 5) live servers (evicting the
oldest — its worktree/PR stay, only the process is stopped), and — at most once per `reap_sweep_age`
(default 30 min) — fully tears down any workspace whose PR(s) are **all** merged/closed. Workspaces
with an OPEN or not-yet-created PR are never touched. If reap evicted *this* task's server, restart it
(workspace.md §6) before you hand out URLs. Harmless in `--lite` mode too.

## 1. Run the iteration contract

Invoke the **`iteration` skill** — it owns implement → simplify → review → commit → push → PR →
considerations → test links. It auto-detects this feature workspace (a
`<worktrees>/<task>/.feature.json` beside the worktree + the config), and therefore:

- uses each involved repo's configured `base_branch` and spans **all** repos in the task;
- loads the workspace's standing `instructions` (config arrays + `.claude/feature/INSTRUCTIONS.md`)
  before writing any code — its step 0;
- picks up the PR's unaddressed review comments (its step 0.5) and answers each one after the push
  (step 4b), so review feedback lands in the same iteration as the user's prompt;
- runs the impartial review gate over every repo it touched, once per iteration, as the last thing
  before the commit (its step 2c) — see the `review` skill;
- persists `<worktrees>/<task>/summary.md` + stamps the session id into `.feature.json` (this is what
  powers the admin dashboard);
- emits pretty `http://<task>.<suffix>/…` deep links (with `localhost:<port>` fallback) as the closing
  test-links block; `--lite` gives how-to-verify instead.

Feature owns only the wrapper: the reap above, keeping every edit inside the `task-<task>` worktree(s),
and never pushing to a base branch. Everything from implement to the final test-links block is the
`iteration` skill's contract — don't restate or fork it here.
