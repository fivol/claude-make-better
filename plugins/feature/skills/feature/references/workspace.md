# Phase 1 — Init workspace

Run only when implementation actually begins. First make sure the workspace config exists (§0),
then anchor `ROOT` to the **workspace root** — the folder that contains `.claude/feature/config.json`
(and the repo checkouts + `worktrees/`). Do NOT rely on `$(pwd)`, which may be a repo subdir.

```bash
ROOT="$(d=$PWD; while [ "$d" != / ] && [ ! -f "$d/.claude/feature/config.json" ]; do d=$(dirname "$d"); done; echo "$d")"
SCRIPTS="${CLAUDE_SKILL_DIR}/scripts"
```

(`ports.py`/`caddyfile.py`/`reap.py`/`admin.py` also self-resolve the root from the config marker, so
they stay correct even when invoked from a subdir — but the `git` commands below need a right `ROOT`.)

## 0. Ensure the workspace config

The skill is config-driven. If `<ROOT>/.claude/feature/config.json` does not exist, create it now,
declaring the repos involved (you can add more later). Schema:

```json
{
  "worktrees_dir": "worktrees",
  "max_live_servers": 5,
  "reap_sweep_age": 1800,
  "proxy": { "enabled": true, "domain_suffix": "localhost",
             "admin_host": "admin.localhost", "admin_port": 7878 },
  "repos": [
    { "name": "<repo-folder>", "base_branch": "<main|dev|…>", "port_band": 18000,
      "frontend": false, "deps_symlink": ["venv"], "env_copy": [".env"],
      "dev_start": "venv/bin/python manage.py runserver 0.0.0.0:{port}" }
  ]
}
```

Per-repo fields:

| Field | Meaning |
|---|---|
| `name` | repo / checkout folder name, directly under `ROOT` |
| `base_branch` | branch to fork from and PR into (e.g. `main`, `dev`) |
| `port_band` | base port; allocator hands out the next free offset (bands ≥1000 apart avoid cross-repo clashes) |
| `frontend` | `true` ⇒ owns the bare `http://<task>.<suffix>` alias; the first frontend present wins |
| `deps_symlink` | dirs symlinked from the main checkout (`node_modules`, `venv`, …) — never build caches |
| `env_copy` | `.env*` files to copy (not symlink) into the worktree |
| `dev_start` | dev-server command with a `{port}` placeholder, run with the worktree as cwd (full mode) |

Pick a short kebab-case `<task>` slug describing the change (e.g. `upload-limit-100mb`). Determine the
involved repos. **One feature may span several repos** — repeat every step below for each.

> If `<worktrees>/<task>/.feature.json` already exists, do NOT recreate anything — read it and resume
> (re-run the iteration). Init is one-time.

> **Mode:** in `--lite` mode skip steps 4–6 (port, FE→BE wiring, dev server) entirely. Steps 1–3 and 7
> run in both modes.

> **If an `Edit`/`Write` is blocked with "this background session hasn't isolated its changes yet —
> call `EnterWorktree` first":** this skill does its *own* isolation via `git worktree add` (below),
> so a session running this skill should be configured to **work in place**, not in harness
> worktree-isolation mode. As an immediate unblock, call `EnterWorktree` once before editing. Don't
> fight the guard by retrying the same `Edit`.

## 1. Create the worktree (branch off fresh remote base)

`base` is the repo's `base_branch` from config.

```bash
git -C "$ROOT/<repo>" fetch origin <base>
git -C "$ROOT/<repo>" worktree add "$ROOT/<worktrees>/<task>/<repo>" -b "task-<task>" "origin/<base>"
```

(`<worktrees>` = the `worktrees_dir` from config, default `worktrees`.)

## 2. Symlink heavy dependencies (do NOT reinstall)

Absolute symlinks into the main checkout, for each dir in the repo's `deps_symlink`. Symlink ONLY
dependencies — never `.next`, `build/`, `.turbo`, or other build caches (those must be per-worktree).

```bash
WT="$ROOT/<worktrees>/<task>/<repo>"
# for each dir in repos[].deps_symlink:
ln -s "$ROOT/<repo>/node_modules" "$WT/node_modules"   # node repos
ln -s "$ROOT/<repo>/venv" "$WT/venv"                    # python repos sharing a venv
```

pnpm repos: symlinking the whole `node_modules` is still valid because its internal symlinks resolve
into the global pnpm store, not the checkout.

## 3. Bring over environment config (copy, don't symlink)

For each file in the repo's `env_copy`: `.env*` files are tiny and may need per-workspace overrides
(port, FE→BE URL), so copy them — symlinking would mutate the main checkout when you override.

```bash
for f in .env .env.local .env.development .env.development.local .env.production; do
  [ -f "$ROOT/<repo>/$f" ] && cp "$ROOT/<repo>/$f" "$WT/$f"
done
```

## 4. Allocate a unique port

```bash
python3 "$SCRIPTS/ports.py" --root "$ROOT" alloc <task> <repo> [<repo> ...]
# prints e.g.  api=18000  web=13000
```

Ports are stable across restarts (stored in `<worktrees>/.ports.json`).

## 5. Wire frontend → workspace backend (only if a backend repo is also in this workspace)

If the feature touches both a backend and a frontend, point the frontend at the workspace backend's
port. Otherwise leave the frontend pointing at the existing dev/prod API.

1. Find the API base env var in the frontend (grep its `.env*` and source). Common conventions:
   `REACT_APP_*` (CRA), `NEXT_PUBLIC_*` (Next.js), `VITE_*` (Vite).
2. Set it in the worktree's `.env.local` (highest precedence for CRA/Next/Vite). Replace any existing
   line for that key, then append:

```bash
KEY=NEXT_PUBLIC_API_URL   # the var you found
sed -i '' "/^$KEY=/d" "$WT/.env.local" 2>/dev/null || true
echo "$KEY=http://localhost:<backend_port>" >> "$WT/.env.local"
```

### 5b. Wire workspace backend → workspace frontend (BE→FE), for redirect flows

FE→BE alone is not enough when the backend builds **absolute URLs back to the frontend** — payment
`success_url`/`cancel_url`, OAuth callbacks, links in emails. Those read a backend env (commonly
`FRONT_URL`, sometimes `FRONTEND_URL` / `SITE_URL` / `*_REDIRECT_URI`) that, copied from the main
`.env`, still points at the generic local frontend (e.g. `http://localhost:3000`). Left unchanged,
the flow leaves the workspace mid-redirect, breaking same-origin state (anon token, localStorage).

So when a backend + a frontend share the workspace, also point the backend's redirect-base env(s) at
the **workspace frontend's pretty URL** (same origin the user browses). Grep the backend for the
var(s) first (`grep -rniE 'FRONT_URL|FRONTEND|SITE_URL|REDIRECT_URI' .env settings/`):

```bash
BE_WT="$ROOT/<worktrees>/<task>/<backend>"
sed -i '' "/^FRONT_URL=/d" "$BE_WT/.env" 2>/dev/null || true
echo "FRONT_URL=http://<task>.<suffix>" >> "$BE_WT/.env"   # the workspace frontend origin
```

`.env` is read at process start, so set this **before** launching the backend in §6 (or restart it
after). External providers must accept the URL — `*.localhost` is fine for most test-mode/localhost-dev
configs; if one rejects it, fall back to `http://localhost:<frontend_port>` and note the origin caveat.

## 6. Start the dev server on the unique port (detached — survives the turn)

When the agent runs as a one-shot `claude -p` turn, a plain `cmd &` job would die the moment the turn
ends. Start the server through `serve.py` instead: it detaches the process into its own session
(reparented to init/launchd, so it outlives the agent) and makes its PID == its process-group id, so
finish/reap can later kill the whole tree (`kill -- -<pid>` catches worker children). It prints the
PID — capture it into `.feature.json` `dev_pid`. Never edit `package.json` to set the port; pass it
via CLI/env.

Use the repo's `dev_start` command (from config), substituting `{port}`:

```bash
WT="$ROOT/<worktrees>/<task>/<repo>"
# example dev_start values (run with cwd=$WT):
#   python:  venv/bin/python manage.py runserver 0.0.0.0:{port}
#   CRA:     env PORT={port} BROWSER=none DANGEROUSLY_DISABLE_HOST_CHECK=true npm start
#   Next.js: node_modules/.bin/next dev -p {port}
PID=$(python3 "$SCRIPTS/serve.py" --cwd "$WT" --log "$WT/<repo>.dev.log" -- <dev_start with {port} filled in>)
```

(env-prefixed vars must go through `env` — `serve.py` execs directly, with no shell.)

Wait for the server to be ready before telling the user the URL — use `serve.py wait` (an in-process
log poll), **never a bash `sleep N && tail` loop**: the harness blocks foreground `sleep`, and fixed
sleeps are flaky.

```bash
python3 "$SCRIPTS/serve.py" wait --log "$WT/<repo>.dev.log" --timeout 180
# exit 0 = ready · 1 = timeout · 2 = compile/start failure (prints the log tail)
```

Then write `$PID` into `.feature.json` `.repos.<repo>.dev_pid`. If a later iteration finds the server
dead (`dev_pid` cleared by reap, or `kill -0 <dev_pid>` fails), restart it exactly the same way. (For
any other wait-for-a-condition need, use the `Monitor` tool with an until-loop — not `sleep`.)

## 6b. Refresh the pretty-URL proxy

After ports are allocated and servers are up, regenerate the Caddyfile and hot-reload so
`http://<task>.<suffix>` works (no sudo). See `proxy.md` for the scheme and one-time setup.

```bash
python3 "$SCRIPTS/caddyfile.py" --root "$ROOT" --reload
```

Give the user the pretty URL (`http://<task>.<suffix>/…`) as the primary one; keep `localhost:<port>`
in state as the fallback. If caddy isn't set up yet, the reload is a no-op — tell the user to run
`scripts/proxy-setup.sh` once, then fall back to `localhost:<port>`.

## 7. Write workspace state

Save `<worktrees>/<task>/.feature.json` so later iterations and finish are reliable even after context
is summarized:

```json
{
  "task": "<task>",
  "mode": "<full|lite>",
  "session_id": null,
  "repos": {
    "<repo>": {
      "branch": "task-<task>",
      "base": "<base_branch>",
      "port": <port>,
      "host": "<repo>.<task>.<suffix>",
      "url": "http://localhost:<port>",
      "pr": null,
      "dev_pid": <pid>
    }
  }
}
```

Update `pr` once the PR is created (Phase 2), and `dev_pid` whenever you (re)start a server.
`session_id` is stamped each iteration (see `iterate.md` §4b) so the admin dashboard can resume the
right chat. In `--lite` mode set `mode: "lite"` and leave `port`, `url`, `dev_pid` as `null`.

After init completes, immediately proceed to the **first iteration** (`iterate.md`).
