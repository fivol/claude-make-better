# Pretty `*.localhost` URLs (Caddy reverse proxy)

Lets you open `http://<task>.localhost/en/main` instead of `http://localhost:<port>`.
**Full mode only** — lite mode has no servers, so no proxy. The URL suffix is `proxy.domain_suffix`
from config (default `localhost`); below assumes the default.

## How it works

Dev servers keep running on their real ports (from `.ports.json`). Caddy listens on `:80` and
reverse-proxies by hostname to those ports, rewriting `Host` → `localhost` so dev-server host checks
pass without touching the repos. Chrome resolves `*.localhost` → `127.0.0.1` itself, so there is
**no `/etc/hosts` and no DNS setup**.

## Host scheme (generated, see `scripts/caddyfile.py`)

| URL | Goes to |
|---|---|
| `http://<task>.<suffix>` | the task's primary frontend (the first repo with `frontend: true` present in the task) |
| `http://<repo>.<task>.<suffix>` | that specific repo (e.g. `api.upload-limit.localhost` for the backend) |

## One-time setup (user runs once, needs sudo once)

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/proxy-setup.sh"
```

Installs caddy, makes the brew Caddyfile `import` the generated `<worktrees>/Caddyfile`, and starts
caddy as a root launchd service (`sudo brew services start caddy`) so it can bind `:80`. After this,
per-task reloads use the local admin API and need **no sudo**. Run it from inside the workspace (so it
finds `.claude/feature/config.json`).

## Per-task (done by the skill, no sudo)

Whenever ports change (init, finish), regenerate and hot-reload:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/caddyfile.py" --root "$ROOT" --reload
```

## Gotchas

- **Chrome works out of the box.** Safari/`curl` do **not** resolve `*.localhost` by default — for
  those add `/etc/resolver/localhost` or an `/etc/hosts` line, or just use `localhost:<port>` from
  `.feature.json`.
- **CRA / webpack**: start it with `DANGEROUSLY_DISABLE_HOST_CHECK=true` as a backstop — the
  `Host: localhost` rewrite already satisfies the check, but webpack versions vary.
- **HMR / WebSocket** is proxied transparently (the HMR client connects to the page's `<task>.<suffix>`
  origin → Caddy → dev server). If hot reload misbehaves, fall back to the `localhost:<port>` URL.
- If a URL 404s or hangs, confirm caddy is up (`lsof -iTCP:80 -sTCP:LISTEN`) and the dev server is
  alive (`*.dev.log`); re-run the `--reload` command.
