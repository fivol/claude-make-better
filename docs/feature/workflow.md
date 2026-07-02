# feature — workflow & the `iteration` skill

How Feature Mode drives a change from request to merged PR. For the config that powers it, see
[configuration.md](configuration.md); for the dashboard, pretty URLs, and commands, see
[dashboard.md](dashboard.md).

## Feature Mode

Invoked once, the `feature` skill puts the agent into **Feature Mode** for the rest of the session —
you don't re-invoke it per step; the conversation itself drives the phases. Each feature/fix is built
in an isolated `git worktree` under `<worktrees>/<task>/`, on its own stable port, and lands in its
base branch via a PR. The core contract: by the time you see a summary, the change is already
simplified, committed, pushed, and reflected in the PR — the summary is the *last* thing produced,
never the first.

Add `--lite` for a no-server run — worktree + simplify + commit + push + PR, but no ports, dev servers,
or pretty URLs. Handy for backend-only, config, or docs changes. It's opt-in: pass the flag explicitly.

## The phases

| Phase | What happens |
|---|---|
| **0 · Analyze** | Preflight the toolchain (git, `gh` + auth, config, repos, Caddy). The agent fixes what it can (create the config, install a missing CLI) and tells you the rest (`gh auth login`, cloning a repo, the one-time proxy setup). Then it understands the request and confirms scope — creating nothing else yet. |
| **1 · Init** | `git worktree add` off the fresh base branch, symlink heavy deps (`node_modules`/`venv` — never build caches), copy `.env*`, allocate a unique stable port, start the **detached** dev server, and refresh the proxy. |
| **2 · Iterate** | The **`iteration` skill** runs the contract (below), every prompt. |
| **3 · Finish** | On your go-ahead ("done" / "merge it"): sync the base branch into the task branch (conflicts resolved in the worktree, so the PR reflects what lands and CI runs on it), wait for green CI, merge into base + push, and tear down the worktree / branch / port / proxy. |

Dev servers are launched **detached** (their own session, reparented to launchd) so they survive a
one-shot `claude -p` turn. A self-throttling **reaper** runs at the top of every iteration to cap live
servers (`max_live_servers`) and tear down workspaces whose PRs have all merged — so nothing piles up.

## The `iteration` skill

The per-iteration contract is its own reusable skill, **`feature:iteration`**, and `feature` delegates
Phase 2 to it. Because it's a standalone skill, you can also use it **outside Feature Mode** — ask to
"ship this" / "open a PR for this change" on any branch and it runs the same disciplined loop.

Every iteration, in order, with the chat summary **last**:

1. **Implement** the change in the worktree (or the current branch, standalone).
2. **Simplify** — a real `/simplify` invocation on the changed files (quality only, must not change
   behavior). Mandatory after any significant change; may skip a genuinely minor one — and it declares
   which (`simplify: ✓` / `simplify: skipped (minor)`).
3. **Considerations** — validate each applicable cross-cutting dimension from the config's
   `considerations` list (mobile, RTL, cross-browser…) and report an explicit
   `considerations: mobile ✓ · rtl n/a · …` line. Empty list ⇒ skipped. See
   [configuration.md](configuration.md#considerations) for how to declare them.
4. **Commit + push** — explicit git, per involved repo.
5. **Ensure the PR** exists — created on the first iteration against the repo's base branch; later
   pushes update it automatically.
6. **Summary + considerations + test links** — the summary comes last and ends with clickable deep
   links that open exactly the affected page(s)/endpoint(s).

Inside a feature workspace it also persists `summary.md` + the session id (which power the
[dashboard](dashboard.md)) and hands out pretty `http://<task>.localhost/…` URLs. On a bare branch
(standalone) it targets the repo's default base and gives how-to-verify steps instead of app URLs.

## Self-improving considerations

At **finish**, the agent reviews the session and may propose new `considerations` entries drawn from
what bit this task — a recurring "what about mobile?", an RTL-only bug, a forgotten empty state. They're
added to your config only with your approval, so over time the checklist teaches itself your recurring
blind spots. See [configuration.md](configuration.md#considerations).
