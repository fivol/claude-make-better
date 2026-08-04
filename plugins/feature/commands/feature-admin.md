---
description: Open the Feature admin dashboard — one live view of all feature workspaces
argument-hint: [--port N] [--root DIR]
---

Launch the **Feature admin dashboard**: a single live view of every feature workspace
(repos, PRs + CI, dev-server health & logs, per-task summary, and a copy-able
`claude --resume` command). It is read-only over the skill's state plus start / stop / reap
buttons — merging stays chat-driven.

Work through the steps in order. Both scripts self-anchor to the workspace root (the directory
tree that holds `.claude/feature/config.json`), or take `--root DIR`.

## 1. Is it already running as a service?

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/autostart.py" --status
```

(Pass `--root DIR` here too if the user gave one. Exit 0 means installed and healthy.)

- **Healthy** → it is already up. Tell the user the `url:` line and **stop** — don't start a
  second copy.
- **Installed but degraded** (wrong root, not loaded, nothing answering) → relay the `advice`
  line verbatim; it names the exact fix. Then continue with step 2.
- **Not installed** → continue with step 2.

## 2. Start it for this session

Run it **in the background** (`run_in_background: true`) so the server outlives this turn — do
**not** block waiting on it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/admin.py" --open $ARGUMENTS
```

Tell the user the single dashboard URL the script printed on its first line. The script already
picks the right one: the pretty `http://admin.localhost` when Caddy is up, otherwise the local
`http://127.0.0.1:<port>`. Don't echo both — surface only what it printed.

If the script exits immediately complaining it can't find `.claude/feature/config.json`, tell the
user to run it from inside a configured workspace or pass `--root <workspace-root>`.

## 3. Offer to keep it running (ask once)

Only when step 1 reported **not installed**, `supported: true` and `declined: false` — otherwise
skip this step in silence. Ask the user with **AskUserQuestion** (header `Autostart`), roughly:

> Keep the dashboard running at login? It installs a user LaunchAgent (no sudo) so
> `http://admin.localhost` is always up, even without Claude running.

- **Yes** →
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/autostart.py" --install
  ```
  It writes `~/Library/LaunchAgents/com.fivol.feature-admin.plist` plus the
  `~/.claude/bin/feature-admin` wrapper, takes over the copy you just started, and prints the
  resulting status. Report that line, and mention once that `autostart.py --uninstall` removes it.
- **No** →
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/autostart.py" --decline
  ```
  This records the answer in `<root>/.claude/feature/autostart.json` so you never ask again.
  Say nothing further about it.

Never install autostart without asking: it is a persistent, system-level change.
