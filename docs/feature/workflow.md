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

- **0 · Load the standing instructions** — the config's `instructions` / `repos[].instructions` plus
  `.claude/feature/INSTRUCTIONS.md` (injected whenever the file exists), so the project's house rules
  constrain the code before it's written. Nothing configured ⇒ skipped silently. See
  [configuration.md](configuration.md#instructions).
- **0.5 · Pick up the PR's review feedback** — unaddressed comments on the PR become work items for
  this same iteration, next to your chat prompt. No PR or nothing new ⇒ skipped silently. See
  [PR review feedback](#pr-review-feedback) below.
- **1 · Implement** the change in the worktree (or the current branch, standalone).
- **2 · Simplify** — a real `/simplify` invocation on the changed files (quality only, must not change
  behavior). Mandatory after any significant change; may skip a genuinely minor one — and it declares
  which (`simplify: ✓` / `simplify: skipped (minor)`).
- **3 · Considerations** — validate each applicable cross-cutting dimension from the config's
  `considerations` list (mobile, RTL, cross-browser…) and report an explicit
  `considerations: mobile ✓ · rtl n/a · …` line. Empty list ⇒ skipped. See
  [configuration.md](configuration.md#considerations) for how to declare them.
- **4 · Commit + push** — explicit git, per involved repo.
- **5 · Ensure the PR** exists — created on the first iteration against the repo's base branch; later
  pushes update it automatically. Then **answer** every comment picked up in step 0.5, one reply per
  thread, each citing the commit that settles it.
- **6 · Summary + review feedback + considerations + test links** — the summary comes last and ends
  with clickable deep links that open exactly the affected page(s)/endpoint(s).

Inside a feature workspace it also persists `summary.md` + the session id (which power the
[dashboard](dashboard.md)) and hands out pretty `http://<task>.localhost/…` URLs. On a bare branch
(standalone) it targets the repo's default base and gives how-to-verify steps instead of app URLs.

## PR review feedback

Comments you leave on the PR are treated as **work items, not notifications** — the agent picks them up
at the start of the next iteration and delivers them together with whatever you asked for in chat. You
never have to paste a comment into the chat to get it done.

Per comment the agent decides: implement it · answer it (a question needs no code) · push back with an
argument if it disagrees or sees a better option · say where it belongs if it's out of scope for this
task · ask, as a numbered question, if it's genuinely ambiguous. After the push it replies in every
thread, citing the commit that settles it, and the chat summary gains a **Review feedback** block —
one bullet per comment with an honest verdict (agreed / disagreed and why / a better option / what's
there is justified) and what it actually did. Silent compliance is explicitly ruled out by the
contract: if you're wrong, the agent has to say so.

Two details worth knowing, because they shape the behaviour:

- **`gh` posts as you.** The agent's replies carry your GitHub account, so "who wrote the last comment"
  can't distinguish you from the agent. Instead the agent's replies carry an invisible marker (an HTML
  comment), and a thread counts as unaddressed while its last comment lacks that marker. Consequence:
  on a PR whose replies predate this feature, previously answered threads surface once — the agent sees
  the full thread and simply won't answer twice.
- **Outdated ≠ handled.** A comment goes outdated the moment a fix touches that file, so outdated
  threads are usually the ones just worked on. They're kept, with their diff hunk for context.

By default the agent answers but never resolves threads — resolving stays yours, so the list of open
threads remains your own reading queue. Switch that with `pr_feedback.resolve`; the whole step is
configured under [`pr_feedback`](configuration.md#pr_feedback) and can be turned off there.

## Self-improving considerations and instructions

At **finish**, the agent reviews the session and may propose new entries drawn from what bit this task
— a recurring "what about mobile?", an RTL-only bug, a forgotten empty state → `considerations`; a
correction with one right answer every time ("always reuse the shared `Dropdown`") → `instructions`.
The split is *check you re-run* vs *rule you follow*. They're added to your config only with your
approval, so over time it teaches itself your recurring blind spots and house rules. See
[configuration.md](configuration.md#considerations).
