# Admin dashboard — see & drive all feature workspaces

`scripts/admin.py` is a tiny, dependency-free (stdlib only) local web app that shows every feature
workspace as a card and lets you act on it. It's a *viewer/controller* over the same state the skill
already writes — it never merges or rewrites history.

## Launch

Easiest — the plugin command (starts it in the background and opens the browser):

```
/feature-admin
```

Or run the script directly:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/admin.py" --open      # opens the browser
# or just:
python3 "${CLAUDE_SKILL_DIR}/scripts/admin.py"             # serves on the configured admin_port (default 7878)
```

On startup it prints **one** URL, picking whichever actually works:

- **http://&lt;admin_host&gt;** (default `http://admin.localhost`) when Caddy is up and already serving
  the admin host — the skill's own Caddy always has that host in the generated Caddyfile.
- otherwise **http://127.0.0.1:&lt;admin_port&gt;** (default `7878`) — the plain local URL, always works.

`--port N` overrides the port (forces the local URL, since Caddy proxies the configured `admin_port`).
`--once` prints the workspaces JSON and exits (no server) — handy for scripting.

Run it from inside the workspace (it self-anchors to the root holding `.claude/feature/config.json`),
or pass `--root`.

Launching it while it is already up is a **no-op**: it recognises the running instance (via
`/api/whoami`), prints the same URL and exits 0. A collision only errors out when the port belongs
to something else, or to a dashboard serving a *different* workspace root — both say what to do.

## Autostart (optional, macOS)

`scripts/autostart.py` installs the dashboard as a **user LaunchAgent** — no sudo, no root — so
`http://admin.localhost` is up after every login, with or without Claude running. `/feature-admin`
checks this and offers it once; you can also drive it directly:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/autostart.py" --status      # ✓/⚠/✗ + what to do (exit 0 = healthy)
python3 "${CLAUDE_SKILL_DIR}/scripts/autostart.py" --install     # install (or re-point at this root)
python3 "${CLAUDE_SKILL_DIR}/scripts/autostart.py" --uninstall   # remove the job and its wrapper
```

It writes exactly three things, all removable with `--uninstall`:

| Path | What |
|---|---|
| `~/Library/LaunchAgents/com.fivol.feature-admin.plist` | the launchd job (`RunAtLoad` + `KeepAlive`) |
| `~/.claude/bin/feature-admin` | wrapper the job runs |
| `~/Library/Logs/feature-admin.log` | stdout/stderr of the dashboard |

Three things it gets right that a hand-written plist usually doesn't:

- **Survives plugin upgrades** — the wrapper re-resolves the newest installed plugin version at every
  launch instead of pinning today's `…/cache/make-better/feature/<version>/…` path.
- **`gh` and `caddy` are on `PATH`** — launchd's default `PATH` has no Homebrew, so PR state and CI
  checks would silently go missing.
- **Root is explicit** — the workspace is baked in as `$FEATURE_ROOT` (config.py resolution step 2),
  since a service has no meaningful cwd. `--status` flags it when that root no longer matches.

Installing takes over a dashboard you started by hand (same port), so nothing collides. Declining the
offer is remembered in `<root>/.claude/feature/autostart.json` — the skill won't ask again.

Non-macOS is reported as unsupported and simply skipped; everything else works the same.

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
| summary panel | `<worktrees>/<task>/summary.md` (written each iteration by the `iteration` skill) |
| last agent message | last assistant text turn in the resumable session's `*.jsonl` |

## Actions (and the ones deliberately left manual)

- **start / stop server**, **reap** — real one-click POST actions.
- **finish** (merge into the base) and **free ports** are *not* one-click — finishing is irreversible
  and chat-driven. The card surfaces the `claude --resume …` command instead; continue that chat and
  say your finish word to run Phase 3.
