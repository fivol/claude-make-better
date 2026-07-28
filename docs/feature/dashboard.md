# feature — dashboard, URLs & commands

The tooling around the [workflow](workflow.md). For the config schema, see
[configuration.md](configuration.md).

## Admin dashboard

```
/feature-admin
```

A dependency-free local dashboard — one live view of **every** workspace at once. It opens at
`http://admin.localhost` when the proxy is up, otherwise `http://127.0.0.1:7878` (the configured
`admin_port`).

Each workspace is a card:

- **Repos** — branch, ahead/behind vs base, diffstat, last commit, uncommitted count.
- **PR state + CI** — OPEN / MERGED / CLOSED / DRAFT with the CI check rollup, from `gh`.
- **Dev-server health** — live/down, with **start / stop** buttons, an **open ↗** deep link, and an
  inline log tail.
- **Summary** — the agent-written `summary.md` (what's done / considerations / what to test) with
  click-persisted test checkboxes.
- **Continue the chat** — a copy-able `claude --resume <session-id>`.

It's read-only over the skill's own state plus start / stop / reap buttons — merging stays chat-driven.
The view auto-refreshes and preserves your selection.

## Pretty `*.localhost` URLs (optional)

Pretty `http://<task>.localhost` URLs (instead of `http://localhost:<port>`) need
[Caddy](https://caddyserver.com/) listening on `:80`, reverse-proxying by hostname to each dev server's
real port. Chrome resolves `*.localhost` → `127.0.0.1` itself, so there's no `/etc/hosts` or DNS setup.

The agent wires up and reloads the proxy for you on every task. The **one** thing it can't do is the
first-time privileged setup — it needs `sudo` once to install Caddy and bind `:80`. When that's
required, the agent prints the exact one-time `proxy-setup.sh` command for you to run; after that,
per-task reloads are automatic and sudo-free. Skip it entirely and everything still works on plain
`localhost:<port>` URLs.

Once set up, the host scheme is:

- `http://<task>.localhost` → the task's primary frontend.
- `http://<repo>.<task>.localhost` → a specific repo (e.g. the backend API).

## Commands

Both are optional shortcuts — Feature Mode already invokes them at the right time:

- **`/feature-doctor`** — preflight the toolchain: `git`, `gh` (installed **and** authenticated), the
  workspace config (and the standing instructions in force, when any), each repo's checkout +
  dependency dirs, and (full mode) Caddy. Each problem is
  tagged **[agent]** (the agent fixes it now — create the config, install a missing CLI) or **[user]**
  (only you can — `gh auth login`, clone a missing repo, the one-time proxy setup). Runs automatically
  on entering Feature Mode; run it yourself anytime to re-check.
- **`/feature-admin`** — open the admin dashboard (above) in your browser.
