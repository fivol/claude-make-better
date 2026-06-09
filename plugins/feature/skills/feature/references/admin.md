# Admin dashboard — see & drive all feature workspaces

`scripts/admin.py` is a tiny, dependency-free (stdlib only) local web app that shows every feature
workspace as a card and lets you act on it. It's a *viewer/controller* over the same state the skill
already writes — it never merges or rewrites history.

## Launch

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/admin.py" --open      # opens the browser
# or just:
python3 "${CLAUDE_SKILL_DIR}/scripts/admin.py"             # serves on the configured admin_port (default 7878)
```

- Pretty URL: **http://&lt;admin_host&gt;** (default `http://admin.localhost`, via the same Caddy the
  skill uses — the host is always in the generated Caddyfile; it 502s only while the admin is down).
- Fallback: **http://127.0.0.1:&lt;admin_port&gt;**.
- `--port N` overrides the port for this run.
- `--once` prints the workspaces JSON and exits (no server) — handy for scripting.

Run it from inside the workspace (it self-anchors to the root holding `.claude/feature/config.json`),
or pass `--root`.

## Layout

Master-detail: a **left list** of equal-height cards (live dot, task name, age, and compact badges —
`● N live` · `N open PR` / `merged` · `N repos` · `±N` uncommitted) that scrolls; click one to select
it. The **right pane** shows everything for the selected workspace, top to bottom:

1. **Summary** — renders `<worktrees>/<task>/summary.md` (what's done / what to consider / what to
   test) with click-persisted test checkboxes.
2. **Repositories** (multi-repo features list a block per repo): branch, ahead/behind vs base,
   diffstat, last commit, a **±N uncommitted** badge, the **PR** state chip (OPEN / MERGED / CLOSED /
   DRAFT) + CI rollup (✓/✗/•) from `gh`, and **dev-server** health with **start / stop**, an
   **open ↗** deep link (`http://<task>.<suffix>`), and an inline **log** tail (ANSI-stripped, errors
   highlighted).
3. **Last agent message** — the agent's last *text* reply in the resumable chat (the final tool-only
   turn is skipped), rendered as markdown, with a `when · source` caption. Below it: a copy-able
   `claude --resume <session-id>` — exact when the skill recorded `session_id` (source `recorded`),
   else a best-effort guess reverse-mapped from `~/.claude/projects/**` (source `reverse`).

A **✓ merged · reap** badge appears in the header once all PRs are merged/closed. The view
auto-refreshes every ~7s, preserving the selection, scroll, and any open log.

## Where the data comes from

| Shown | Source |
|---|---|
| repos, ports, PR links, mode | `<worktrees>/<task>/.feature.json` |
| ahead/behind, diffstat, commit, dirty | `git` in each worktree |
| PR state + CI checks | `gh pr view` (cached ~45s) |
| server liveness | `kill -0 <dev_pid>` |
| log tail | `<worktrees>/<task>/<repo>.dev.log` |
| resume command | `.feature.json` `session_id`, else session history |
| summary panel | `<worktrees>/<task>/summary.md` (written each iteration, see `iterate.md` §4b) |
| last agent message | last assistant text turn in the resumable session's `*.jsonl` |

## Actions (and the ones deliberately left manual)

- **start / stop server**, **reap** — real one-click POST actions.
- **finish** (merge into the base) and **free ports** are *not* one-click — finishing is irreversible
  and chat-driven. The card surfaces the `claude --resume …` command instead; continue that chat and
  say your finish word to run Phase 3.
