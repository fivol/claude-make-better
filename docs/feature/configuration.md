# `feature` — configuration

The `feature` plugin is driven by one per-project file, with one optional companion:

```
<workspace-root>/.claude/feature/
├── config.json         # required — defines the workspace and its repos
└── INSTRUCTIONS.md     # optional — standing rules, injected whenever it exists
```

`config.json`'s **presence defines the workspace root** — the folder that holds your repo checkouts (each as a
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
  "instructions": [
    "Never add a dependency without asking first"
  ],
  "considerations": [
    {
      "name": "mobile",
      "when": "any change to UI / markup / styles in a frontend repo",
      "check": "Does this apply to the mobile viewport? If so, verify it's adapted: responsive layout, tap targets, no horizontal scroll, popups/modals fit.",
      "repos": ["web"]
    }
  ],
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
      "dev_start": "venv/bin/python manage.py runserver 0.0.0.0:{port}",
      "instructions": ["Every new endpoint needs a serializer test"]
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
| `instructions` | `[]` | Standing rules every iteration must obey — **strictly an array of strings** (see below). |
| `considerations` | `[]` | Cross-cutting dimensions the agent validates every iteration (see below). Empty ⇒ feature off. |
| `proxy` | see below | Pretty-URL / admin-dashboard settings. |
| `repos` | `[]` | The repos the skill can build in. **Required** — the skill can't run with an empty list. |

## `proxy`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Whether pretty `*.<suffix>` URLs are used (full mode). |
| `domain_suffix` | `"localhost"` | URL suffix. `*.localhost` resolves to `127.0.0.1` in Chrome with no DNS/hosts setup. |
| `admin_host` | `"admin.localhost"` | Hostname the admin dashboard is proxied at. |
| `admin_port` | `7878` | Port the admin dashboard listens on (also its `:127.0.0.1` fallback). |

## `instructions[]`

**Standing rules** the agent follows on every iteration — the project-wide equivalent of a
`CLAUDE.md`, scoped to feature work. Declare a rule once and it holds for every task in the
workspace, without you restating it per request.

Three sources, all optional, all applied **whenever present** — the `iteration` skill assembles them
in its step 0, before any code is written:

| Source | Shape | Use it for |
|---|---|---|
| `instructions` in `config.json` | array of strings — strictly (a bare string is a config error) | short one-line rules, workspace-wide |
| `repos[].instructions` | array of strings | rules that apply only when that repo is touched |
| `.claude/feature/INSTRUCTIONS.md` | free-form markdown, injected verbatim | anything longer: prose, snippets, sections |

No config key points at `INSTRUCTIONS.md` and nothing switches it off: **if the file exists, it is
injected**. Delete it to stop applying it.

### instructions vs considerations

|  | `instructions` | `considerations` |
|---|---|---|
| What it is | a rule you follow | a check you re-run |
| When it applies | while writing the code | after the change, before commit |
| Reported back | never | every iteration: `considerations: mobile ✓ · rtl n/a · …` |
| Example | "no `any` in TS" | "does this work on mobile?" |

Rule of thumb: if the answer is always the same and you'd never want it reported, it's an
instruction. If you have to look at the diff to answer, it's a consideration.

Example:

```json
"instructions": [
  "Never add a runtime dependency without asking first",
  "User-facing copy goes through i18n — no hard-coded strings"
],
"repos": [
  { "name": "web",
    "instructions": ["No `any` in TS", "Reuse the shared `Dropdown` — never write a new one"] }
]
```

### Checking what the agent will actually see

```bash
python3 <plugin>/skills/feature/scripts/config.py --root <workspace-root> --instructions --repos web
```

Prints the assembled block (file contents + config arrays, narrowed to the repos touched), or nothing
when none are configured.

## `considerations[]`

A checklist of **cross-cutting dimensions** the agent must validate on every iteration, before
commit (the `iteration` skill's contract, step 2b). These are the recurring blind spots —
things a feature gets specified *without* (desktop-only, LTR-only, Chrome-only, happy-path-only) and
that then ship broken. Declaring them once here means the agent reports an explicit
`considerations: mobile ✓ · rtl n/a · …` line every iteration and can't silently forget them.

| Field | Required | Meaning |
|---|---|---|
| `name` | ✅ | Short label shown in the summary line (e.g. `mobile`, `rtl`, `cross-browser`, `a11y`). |
| `check` | ✅ | What to actually verify — phrased as an imperative the agent can act on, not just a topic. |
| `when` | — | Free-text applicability condition (e.g. "any UI/style change"). The agent decides per iteration; omit ⇒ always considered applicable. |
| `repos` | — | Restrict applicability to iterations that touch one of these repos (e.g. only frontends). Omit ⇒ any repo. |

Each iteration the agent marks every applicable entry `✓` (verified), `n/a` (not applicable), or `⚠`
(applicable but unverified / needs follow-up). It's also a **self-improving** list: after `finish`,
the agent reviews the session and may propose new entries drawn from what bit this task — added only
with your approval (see `references/finish.md` §11).

Example:

```json
"considerations": [
  { "name": "mobile", "when": "any UI/markup/style change in a frontend repo",
    "check": "Verify the mobile viewport is adapted: responsive layout, tap targets, no horizontal scroll, popups fit.",
    "repos": ["web"] },
  { "name": "rtl", "when": "any UI text / layout change",
    "check": "If the app supports RTL locales, verify the layout mirrors correctly (no hard-coded left/right).",
    "repos": ["web"] },
  { "name": "cross-browser", "when": "non-trivial CSS / web-API usage",
    "check": "Sanity-check Safari/iOS for the change (flex gap, date inputs, sticky, backdrop-filter)." }
]
```

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
| `instructions` | — | Standing rules (array of strings) applied only on iterations that touch this repo — see [`instructions[]`](#instructions). |
| `dev_start` | full mode | Dev-server command, run with the worktree as the working directory. `{port}` is substituted with the allocated port. Tokenized with shell-style splitting (no shell), so env-prefixed vars must go through `env` — e.g. `env PORT={port} BROWSER=none npm start`. |

### `dev_start` examples

| Stack | `dev_start` |
|---|---|
| Django | `venv/bin/python manage.py runserver 0.0.0.0:{port}` |
| Create React App | `env PORT={port} BROWSER=none DANGEROUSLY_DISABLE_HOST_CHECK=true npm start` |
| Next.js | `node_modules/.bin/next dev -p {port}` |
| Vite | `node_modules/.bin/vite --port {port}` |

## Inspecting the merged result

Ask the agent to inspect the merged config — it runs the skill's `config.py` and prints the result as
JSON, including the resolved `_root`, `_override_path`, and `_override_applied`. Handy when a setting
doesn't seem to apply: you'll see whether your file was picked up at all.

## Environment overrides

| Env var | Overrides |
|---|---|
| `FEATURE_ROOT` | Workspace root (skips the config-marker walk-up). |
| `FEATURE_MAX_SERVERS` | `max_live_servers` (reaper). |
| `FEATURE_REAP_SWEEP_AGE` | `reap_sweep_age` (reaper). |
