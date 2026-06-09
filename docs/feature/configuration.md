# `feature` — configuration

The `feature` plugin is driven by one per-project file:

```
<workspace-root>/.claude/feature/config.json
```

Its **presence defines the workspace root** — the folder that holds your repo checkouts (each as a
sibling folder) and the `worktrees/` tree the skill creates. The scripts auto-resolve the root by
walking up from the current directory to the nearest ancestor containing this file (override with
`--root DIR` or the `FEATURE_ROOT` env var).

Values are deep-merged over the plugin's shipped `defaults.json` (override wins; lists are replaced
wholesale, so your `repos` list replaces the empty default).

## Full schema

```json
{
  "worktrees_dir": "worktrees",
  "max_live_servers": 5,
  "reap_sweep_age": 1800,
  "output_language": "the user's language",
  "proxy": {
    "enabled": true,
    "domain_suffix": "localhost",
    "admin_host": "admin.localhost",
    "admin_port": 7878
  },
  "repos": [
    {
      "name": "api",
      "base_branch": "main",
      "port_band": 18000,
      "frontend": false,
      "deps_symlink": ["venv"],
      "env_copy": [".env"],
      "dev_start": "venv/bin/python manage.py runserver 0.0.0.0:{port}"
    },
    {
      "name": "web",
      "base_branch": "main",
      "port_band": 13000,
      "frontend": true,
      "deps_symlink": ["node_modules"],
      "env_copy": [".env", ".env.local"],
      "dev_start": "node_modules/.bin/next dev -p {port}"
    }
  ]
}
```

## Top-level keys

| Key | Default | Meaning |
|---|---|---|
| `worktrees_dir` | `"worktrees"` | Directory (under the root) for worktrees, the port registry, and the generated Caddyfile. |
| `max_live_servers` | `5` | Reaper cap on concurrent dev servers; the oldest beyond this are stopped (worktree/PR kept). |
| `reap_sweep_age` | `1800` | Min seconds between networked PR-state teardown sweeps (throttle). |
| `output_language` | `"the user's language"` | Hint for the language of agent output and the persisted `summary.md`. |
| `proxy` | see below | Pretty-URL / admin-dashboard settings. |
| `repos` | `[]` | The repos the skill can build in. **Required** — the skill can't run with an empty list. |

## `proxy`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Whether pretty `*.<suffix>` URLs are used (full mode). |
| `domain_suffix` | `"localhost"` | URL suffix. `*.localhost` resolves to `127.0.0.1` in Chrome with no DNS/hosts setup. |
| `admin_host` | `"admin.localhost"` | Hostname the admin dashboard is proxied at. |
| `admin_port` | `7878` | Port the admin dashboard listens on (also its `:127.0.0.1` fallback). |

## `repos[]`

A repo's **checkout folder name must equal its `name`**, located directly under the workspace root.

| Field | Required | Meaning |
|---|---|---|
| `name` | ✅ | Repo / checkout folder name. |
| `base_branch` | ✅ | Branch to fork the task branch from and open the PR against (e.g. `main`, `dev`). |
| `port_band` | full mode | Base port for this repo; the allocator hands out the next free offset per task. Keep bands ≥1000 apart so parallel workspaces never collide across repos. |
| `frontend` | — | `true` ⇒ this repo owns the bare `http://<task>.<suffix>` alias. The first `frontend: true` repo present in a task wins; others get `http://<repo>.<task>.<suffix>`. |
| `deps_symlink` | — | Directories symlinked from the main checkout into the worktree (e.g. `node_modules`, `venv`). Never list build caches (`.next`, `build`, `.turbo`) — those must be per-worktree. |
| `env_copy` | — | `.env*` files copied (not symlinked) into the worktree, so per-workspace overrides (port, FE→BE URL) don't mutate the main checkout. |
| `dev_start` | full mode | Dev-server command, run with the worktree as the working directory. `{port}` is substituted with the allocated port. Tokenized with shell-style splitting (no shell), so env-prefixed vars must go through `env` — e.g. `env PORT={port} BROWSER=none npm start`. |

### `dev_start` examples

| Stack | `dev_start` |
|---|---|
| Django | `venv/bin/python manage.py runserver 0.0.0.0:{port}` |
| Create React App | `env PORT={port} BROWSER=none DANGEROUSLY_DISABLE_HOST_CHECK=true npm start` |
| Next.js | `node_modules/.bin/next dev -p {port}` |
| Vite | `node_modules/.bin/vite --port {port}` |

## Inspecting the merged result

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root /path/to/workspace
```

Prints the merged config as JSON, including the resolved `_root`, `_override_path`, and
`_override_applied` — handy when a setting doesn't seem to apply.

## Environment overrides

| Env var | Overrides |
|---|---|
| `FEATURE_ROOT` | Workspace root (skips the config-marker walk-up). |
| `FEATURE_MAX_SERVERS` | `max_live_servers` (reaper). |
| `FEATURE_REAP_SWEEP_AGE` | `reap_sweep_age` (reaper). |
