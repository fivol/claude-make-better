# Claude Code plugins by fivol

> A small [Claude Code](https://claude.com/claude-code) plugin marketplace — add it once, install what you want.

```
/plugin marketplace add fivol/claude-make-better
```

| Plugin | Install | What it does |
|---|---|---|
| [**make-better**](#make-better) | `/plugin install make-better@make-better` | Audit & improve your codebase on autopilot — one command, nine topics, fixes on a branch. |
| [**feature**](#feature) | `/plugin install feature@make-better` | Build each feature/fix in an isolated git-worktree workspace — unique port, pretty URL, PR-per-iteration, live admin dashboard. |

---

# make-better

> **Audit and improve your codebase on autopilot — one command, nine topics, fixes on a branch.**

A [Claude Code](https://claude.com/claude-code) plugin that audits and improves an existing codebase. One command picks the oldest subsystems of your project and reviews them across nine built-in topics — bugs, DRY, architecture, consistency, efficiency, tests, docs sync, completeness, and (optionally) security — plus any custom topics you add for your own conventions. Fixes are applied as merge commits on your current branch — never pushed, easy to inspect or undo.

Everything is configurable per-project: staleness thresholds, parallelism, agent models, ignored directories, the topic list itself. Drop a JSON file at `.claude/make-better/config.json` and you're done — see [Configuration](#configuration) and [Custom review topics](#custom-review-topics) below.

## Install

```
/plugin marketplace add fivol/claude-make-better
/plugin install make-better@make-better
```

## Quick start

```
/make-better
```

That's it. On a fresh repo it discovers your subsystems, then reviews the oldest ones. On subsequent runs it reuses the registry and goes straight to review.

## Usage

```
/make-better                  # smart defaults — usually 3 oldest systems
/make-better 8                # review 8 systems
/make-better flutter          # only systems matching "flutter"
/make-better flutter 4        # 4 systems matching "flutter"
```

### Flags

| Flag | What it does |
|---|---|
| `--no-discover` | skip the discover phase, go straight to review |
| `--rebuild` | force a full re-discovery before review |
| `--discover-only` | refresh the registry but don't review |
| `--yes` (`-y`, `--auto`) | unattended: no plan mode, no prompts, runs to completion |

## Example output

A real run on a medium-sized monorepo:

```
Total: 104 findings across 5 systems.
  - 13 bug fixes (applied automatically)
  - 14 DRY refactors
  - 11 architecture cleanups
  - 13 consistency fixes
  -  6 efficiency wins
  - 16 tests added
  - 18 doc-sync updates
  - 10 completeness fixes
  -  3 security
```

Each system gets its own implementer branch (`systems-review/<system>`), and the agent merges them back into your current branch with `--no-ff` merge commits. Branches are deleted after merge, worktrees auto-cleaned, lint+test runs once at the end. Nothing is pushed — you review with `git log` / `git diff` and either `git push` or `git reset --hard <pre-run sha>`.

> **Tip:** run on a feature branch, not directly on `main` / `master`. The agent merges into whatever branch you're on.

## Unattended runs

By default Make Better pauses for review at key points (proposed registry, per-system plan). For cron, `/schedule`, and any other unattended use, pass `--yes`:

```
/make-better --yes 5
```

What changes:

- Plan mode is skipped — the agent runs the computed plan as-is.
- Stale lockfiles are auto-removed.
- Ambiguous decisions don't block: the agent picks the safe default if there is one, otherwise skips the affected system and lists it under "Skipped — human decision needed" in the final report.
- Hard errors still abort.

Successful fixes still land as merge commits on your current branch — same flow as interactive runs. Skipped systems' branches are cleaned up; their status goes into the registry and the final report. Review with `git log` after the run; nothing is pushed.

## Set it and forget it

If you have a scheduler available — for example the [`/schedule`](https://github.com/anthropics/claude-code) skill from another plugin — point it at `/make-better --yes`:

```
/schedule create "0 9 * * 1" /make-better --yes 5
```

Otherwise use `cron` with Claude Code's non-interactive mode (consult [Claude Code docs](https://docs.claude.com/en/docs/claude-code) for the exact CLI invocation in your version). Either way: every Monday at 9am, 5 stale systems get reviewed, fixes merged into the current branch (unpushed), ready for your morning coffee.

## Configuration

Drop a JSON file at `<repo-root>/.claude/make-better/config.json` to customize without touching the plugin. Every key is optional — anything missing falls back to plugin defaults.

The most useful knobs:

- `registry_path` — where to keep the systems registry. Default: `docs/SYSTEMS.md`.
- `review.user_language` — language for every user-facing message (`"en"`, `"ru"`, `"es"`, …). Default: `"en"`.
- `review.review_stale_after_days` — re-audit a system after this many days. Default: `30`.
- `review.default_systems_per_run` — how many systems to review when count isn't specified. Default: `3`.
- `review.topics_required` — topics that always run on every system. Listing topics here **replaces** the default list — include built-ins you want to keep alongside your custom ones.
- `review.topics_optional` — topics that run when applicable (currently just `security`). Same replace-not-merge semantics.
- `instructions` — standing house rules (array of strings) handed to every sub-agent, so they're enforced during review *and* respected while fixes are written. For anything longer than a line, put it in `.claude/make-better/INSTRUCTIONS.md` — that file is injected whenever it exists.

Copy and edit:

```json
{
  "registry_path": "docs/SYSTEMS.md",
  "review": {
    "user_language": "en",
    "review_stale_after_days": 30,
    "default_systems_per_run": 3,
    "topics_required": [
      "bugs", "completeness", "dry", "architecture",
      "consistency", "efficiency", "tests", "docs-sync"
    ],
    "topics_optional": ["security"]
  }
}
```

Full schema (parallelism, model selection, ignore_dirs, doc hint paths, all the rest): **[docs/configuration.md](docs/configuration.md)**.

## Custom review topics

Add your own audit topics — perf budgets, accessibility, internal style guides, anything you want flagged on every review.

1. Drop a prompt at `.claude/make-better/topics/<name>.md`.
2. Add `<name>` to `topics_required` (or `topics_optional`) in your config.

> **Heads up:** `topics_required` is **replaced** by your config, not merged element-wise. List every topic you want — built-ins you keep AND your additions. The same applies to `topics_optional`.

Done. Full guide with prompt template: **[docs/custom-topics.md](docs/custom-topics.md)**.

## Updating

```
/plugin marketplace update make-better
```

Or use the interactive `/plugin` UI.

## More

- **[How `/systems-review` works](docs/systems-review.md)** — phases, parallelism, worktrees, lockfiles.
- **[How `/systems-discover` works](docs/systems-discover.md)** — registry format, scan agents, cross-cutting merge.
- **[Configuration reference](docs/configuration.md)** — every knob, with defaults and examples.
- **[Custom review topics](docs/custom-topics.md)** — add your own audit dimensions.

For finer-grained control, the underlying commands are also available directly:

```
/systems-discover [<area>] [--rebuild]    # registry maintenance
/systems-review   [count] [subsystem]     # audit only
```

## Bonus: `/meta-review` — audit how you work with Claude

Beyond auditing your *codebase*, the plugin also ships **`/meta-review`** — a retrospective audit of your own Claude Code *sessions*. It fans out review subagents across five lenses (workflow & repetition, errors & dead-ends, instruction adherence, skill & automation gaps, tech & approach quality), hands you a color-coded prioritized list (🔴 important / 🟡 significant / 🟢 minor), and applies what you pick. Each run is logged to `.meta-review.jsonl` so the next one resumes from where the last stopped.

```
/meta-review              # current project, since last review (else past 7 days)
/meta-review all          # every project under ~/.claude/projects
/meta-review 14d          # force a 14-day window
```

Prefers the `meta-cc` MCP tools (if installed) to aggregate session history, with raw session-JSONL parsing as a fallback.

## Requirements

- Claude Code with plugin marketplace support
- `git`
- `python3` (or `python`) — used by the config loader

## Status & feedback

Make Better is in **active development** (0.x). Behavior, defaults, and config schema may change between minor versions. If you're running it on a real codebase — please tell me when something goes sideways.

[**Open an issue →**](https://github.com/fivol/claude-make-better/issues)

What's especially useful to report:

- **Wrong findings** — the agent flagged something that wasn't a real issue, or missed something obvious. Paste the system + topic + the finding (or what you expected).
- **Stuck runs** — `/make-better` hung, looped, or exited with a confusing error. Include `--yes` mode if relevant; copy the last ~50 lines of the agent transcript.
- **Bad merges** — a system's fix broke an unrelated part of the codebase, or the integration lint+test missed a regression. Branch name + diff are gold.
- **Config that didn't apply** — your override at `.claude/make-better/config.json` was ignored. Run the loader-debug recipe in [docs/configuration.md](docs/configuration.md#inspecting-the-merged-result) and paste the `_meta` block.
- **UX ideas** — something feels clunky, a flag you wish existed, a default you'd flip. Equally welcome.

A reproduction (`/make-better` invocation, anonymized snippet of the system being reviewed, observed vs expected) makes any of these 10× easier to fix.

---

# feature

> **Every feature/fix in its own isolated worktree — unique port, pretty URL, and a PR per iteration.**

A [Claude Code](https://claude.com/claude-code) plugin that turns "build/fix X" into a disciplined,
reviewable flow. Invoked once, it puts the agent into **Feature Mode** for the session: each change is
built in an isolated `git worktree` (deps symlinked, never reinstalled), runs on its own stable port
behind a pretty `http://<task>.localhost` URL, and lands in a PR — simplified, committed, and pushed
**before** you ever see the summary. A live admin dashboard shows every workspace at a glance.

It's config-driven, so it works for any single- or multi-repo workspace.

## Install

```
/plugin marketplace add fivol/claude-make-better
/plugin install feature@make-better
```

## Quick start

1. Create a config at your workspace root — `<workspace-root>/.claude/feature/config.json` — declaring
   your repos:

   ```json
   {
     "repos": [
       { "name": "web", "base_branch": "main", "port_band": 3000, "frontend": true,
         "deps_symlink": ["node_modules"],
         "dev_start": "node_modules/.bin/next dev -p {port}" }
     ]
   }
   ```

   The workspace root is the folder holding your repo checkouts (each a sibling folder named after its
   `name`); the config's presence marks that root. Add more repos for a multi-repo feature — full
   schema (proxy, `instructions`, `considerations`, env-copy, reaper…) in
   **[configuration.md](docs/feature/configuration.md)**.

   Standing house rules go in `instructions` (an array of strings, workspace-wide or per repo) or in
   `.claude/feature/INSTRUCTIONS.md` — free-form markdown that's injected into every iteration
   whenever the file exists, so you never restate the same rule per request.

2. Just ask for a feature — "let's add a dark-mode toggle", "fix the upload limit". The agent enters
   Feature Mode, spins up the worktree(s) + server(s), and from then on every iteration is
   committed/pushed into a PR automatically.

3. When you're happy, say "done" / "merge it" — it syncs the base branch into the task branch (CI runs
   on the integrated code), merges, and cleans everything up.

> Add `--lite` for a no-server run (worktree + simplify + commit + push + PR, but no ports / dev
> servers / pretty URLs) — handy for backend-only or docs changes.

## How it works

**Analyze** (preflight the toolchain, confirm scope) → **Init** (worktree, deps, port, detached dev
server, proxy) → **Iterate** (the `iteration` skill: pick up PR comments → implement → `/simplify` →
**review** → considerations → commit → push → PR → answer every comment → deep test links, every
prompt) → **Finish** (sync base, **final review of the integrated branch**, green CI, merge, clean up).

Comments you leave on the PR are part of that loop: the agent picks up the unaddressed ones next
iteration, does or argues with each, replies in the thread citing the fixing commit, and reports an
honest verdict per comment in the summary — see
**[PR review feedback](docs/feature/workflow.md#pr-review-feedback)**.

Before anything is committed it goes through the **review gate** — a subagent that never saw the
conversation, hunts correctness bugs before cleanups, verifies each candidate before believing it,
and fixes what survives. You get a cleaned diff plus a one-line tally, not a list of homework; the
only thing that reaches the chat is what the reviewer refused to decide alone. Its finders literally
cannot edit your code (no `Edit`, no `Write` — fixing happens once, at the end), reasoning runs on
Opus while retrieval runs on Sonnet, and verification is batched so it actually runs. It runs again on
the whole branch before the merge, where it is the only pass that ever sees the conflict resolutions —
see **[the review gate](docs/feature/workflow.md#the-review-gate)**.

## Docs

- **[Workflow & the `iteration` skill](docs/feature/workflow.md)** — the phases, the per-iteration
  contract, the reusable **standalone** `iteration` skill, PR review feedback, and the considerations
  checklist.
- **[Dashboard, URLs & commands](docs/feature/dashboard.md)** — the admin dashboard (`/feature-admin`),
  pretty `*.localhost` URLs, and the `/feature-doctor` preflight.
- **[Configuration](docs/feature/configuration.md)** — full config schema: per-repo fields,
  `instructions` + `INSTRUCTIONS.md`, `considerations`, proxy, reaper caps, env overrides.

## Requirements

- Claude Code with plugin marketplace support
- `git` (with `git worktree`), `gh` (GitHub CLI, authenticated — for PRs)
- `python3` — used by the skill's scripts
- macOS/Linux. Pretty URLs additionally need Caddy + Homebrew (optional)

## License

MIT
