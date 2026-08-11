---
description: Open the admin dashboard — one live view of all task workspaces
argument-hint: "[--port N] [--root DIR]"
---

Launch the **admin dashboard**: a single live view of every task workspace
(repos, PRs + CI, dev-server health & logs, per-task summary, and a copy-able
`claude --resume` command). It is read-only over the skill's state plus start / stop / reap
buttons — merging stays chat-driven.

Run it **in the background** (`run_in_background: true`) so the server outlives this turn — do
**not** block waiting on it. Start it from the workspace root (the directory tree that holds
`.claude/feature/config.json`; the script self-anchors, or pass `--root DIR`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/admin.py" --open $ARGUMENTS
```

Then tell the user the single dashboard URL the script printed on its first line and stop. The
script already picks the right one: the pretty `http://admin.localhost` when Caddy is up,
otherwise the local `http://127.0.0.1:<port>`. Don't echo both — surface only what it printed.

If the script exits immediately complaining it can't find `.claude/feature/config.json`, tell the
user to run it from inside a configured workspace or pass `--root <workspace-root>`.
