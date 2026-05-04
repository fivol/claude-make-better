# How `/systems-review` works

`/systems-review` is the audit-and-fix half of Make Better. It picks N stale systems from the registry, audits each across multiple topics in parallel, produces a per-system plan, and applies the resulting fixes in isolated git worktrees.

This document explains what actually happens under the hood. For the user-facing flags and examples, see the [README](../README.md).

## Inputs

```
/systems-review [count] [subsystem] [--yes]
```

- `count` — how many systems to review this run (clamped to `max_systems_per_run`).
- `subsystem` — semantic filter applied to section names, system names, and notes. Generous matching: `flutter` matches "Flutter App" section AND any system with "flutter" in its notes.
- `--yes` (alias `-y`, `--auto`) — non-interactive mode. See "Non-interactive behavior" below.

## Phases

### Phase 0 — Bootstrap

1. **Verify registry** — reads `<registry_path>` (default `docs/SYSTEMS.md`). If missing, stops with: "Run `/systems-discover` first."
2. **Parse registry** — walks the markdown, extracts ordered list of `{ section, name, last_review, status, blocker, areas, notes }` entries.
3. **Build candidate pool** — applies filters in order:
   1. Subsystem filter (semantic).
   2. Drop `status: needs_user_decision` — these need human resolution.
   3. Drop systems locked by other parallel runs.
   4. Drop systems that overlap files in your working tree (avoids merge conflicts with your in-progress work — overlap counts even for untracked files).
   5. Drop systems with `last_review` newer than `(today - review_stale_after_days)`.
4. **Detect stale lockfiles** — peer lockfiles older than `stale_lockfile_after_hours` (default 3h) are flagged. With `--yes` they're auto-removed; otherwise the user is prompted.
5. **Sample** — picks `count` systems from the pool, weighted toward oldest `last_review` (no review = oldest).
6. **Write own lockfile** — `docs/.systems-review.<filter_slug>-<timestamp>.lock` with the list of systems being reviewed. Cleaned up on every exit path (success, abort, exception).

### Phase 1 — Topic-driven review (parallel)

For each picked system, dispatches a **review agent** in parallel (`max_parallel_review_agents`, default 4). Each review agent:

1. Reads every topic prompt from `_topics` (resolved by the loader — see [custom topics](custom-topics.md)).
2. Dispatches one **topic agent** per topic in parallel. Each topic agent runs the topic-specific prompt against the system's `areas:` and returns a JSON array of findings (file, line, issue, severity, fix).
3. Consolidates all topic findings into a single per-system plan: a `user_spec` (rendered bullet list) and a `detailed_plan` (full instructions for the implementer).
4. Returns one of: `proceed`, `empty_plan`, `system_removed`, `needs_user_decision`.

### Phase 2 — Plan mode

Shows the consolidated plan for every system in plan mode. The user can:

- Approve as-is.
- Drop behavior changes flagged in "Needs your attention".
- Edit free-form ("rename this path", "skip this system", "this is wrong because…").
  - **Trivial edits** (drop a step, reorder, rename a path): updated silently in memory, plan re-rendered, prompt re-shown.
  - **Non-trivial edits** (replace approach, "are you sure?"): the agent investigates by re-dispatching a focused topic agent, replies with consequences and alternatives, and waits for confirmation before updating.
- Cancel.

With `--yes`, this phase is skipped — the plan is treated as approved-as-is.

### Phase 3 — Implementation (parallel, in worktrees)

For every approved system:

1. Creates an isolated git worktree at `.git/worktrees/systems-review/<system>/`.
2. Branch: `systems-review/<all|filter>-<timestamp>/<system>`.
3. Dispatches an **implement agent** (`max_parallel_implement_agents`, default 2) inside the worktree with the `detailed_plan`.
4. Agent applies fixes, runs tests if available, commits.
5. Worktree stays in place — nothing gets force-merged into your work. You decide what to land.

Parallelism is intentional: separate worktrees mean concurrent implement agents never see each other's changes. Even if two systems touch the same file, they each work on their own branch and merge conflicts (if any) surface when you decide to integrate.

### Phase 4 — Finalize

For each system whose implement phase succeeded:

1. The worktree's branch is left in place. Branch name is reported back so the user can `git diff systems-review/...`.
2. Updates `last_review` for that system in `docs/SYSTEMS.md` to today's date.
3. If implement returned `needs_user_decision` mid-flight (e.g. encountered ambiguity that wasn't in the plan), the system gets `status: needs_user_decision` and a `blocker:` field. `last_review` is **not** stamped — the system stays stale until a human deals with it.

If the implementation failed unrecoverably and `--yes` is off, the user is asked. With `--yes`, the system is added to "Skipped — human decision needed" and the run continues.

### Phase 5 — Report

Final summary aggregates:

- Total findings, broken down by topic.
- Per-system: branch name, what was done, manual verification steps from the plan.
- Systems with `status: needs_user_decision` — what blocked them.
- (`--yes` only) Systems skipped because no safe default could be picked.

The user's main action after a run: `git diff` the review branches, run any manual verifications listed, merge what looks good.

## Concurrency model

Three layers of parallelism, all bounded:

| Layer | Limit | Notes |
|---|---|---|
| Review agents | `max_parallel_review_agents` (default 4) | one per system |
| Topic agents (per review) | unbounded across topics | typically 8–9 topics |
| Implement agents | `max_parallel_implement_agents` (default 2) | one per approved system |

Multiple `/systems-review` runs can execute in parallel safely:

- Each run writes its own lockfile listing the systems it owns.
- New runs read every peer lockfile in `lockfile_dir` and skip systems already locked.
- Working-tree filter prevents conflicts with the human's in-progress changes.

## Non-interactive behavior (`--yes`)

| Decision point | Default behavior | `--yes` behavior |
|---|---|---|
| Plan mode (Phase 2) | wait for approval | skip, treat as approved |
| Stale peer lockfile | prompt y/n | auto-remove with log line |
| AskUserQuestion w/ safe default | ask | pick safe default |
| AskUserQuestion w/o safe default | ask | skip the affected unit, log under "skipped — human decision needed" |
| Hard error (missing config, etc.) | abort | abort |
| `status: needs_user_decision` system | excluded from pool | excluded from pool |

`--yes` only suppresses prompts that have an answer the agent can produce. It never resolves decisions humans previously deferred.

## Config knobs

The full schema is in [configuration.md](configuration.md). The ones specific to `/systems-review`:

- `review_stale_after_days` (14) — re-audit after this many days.
- `default_systems_per_run` (3) — count when not specified.
- `max_systems_per_run` (8) — clamp.
- `max_parallel_review_agents` (4) — review-agent concurrency.
- `max_parallel_implement_agents` (2) — implement-agent concurrency.
- `topic_agent_model` (sonnet) / `review_agent_model` (opus) / `implement_agent_model` (opus).
- `lockfile_dir` (docs).
- `stale_lockfile_after_hours` (3).
- `branch_prefix` (systems-review).
- `topics_required` / `topics_optional`.
- `user_language` — render every user-facing message in this language.
