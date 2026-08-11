# Claude Code plugins by fivol

> A small [Claude Code](https://claude.com/claude-code) plugin marketplace — add it once, install what you want.

```
/plugin marketplace add fivol/claude-make-better
```

| Plugin | Install | What it does |
|---|---|---|
| [**make-better**](#make-better) | `/plugin install make-better@make-better` | Audit & improve your codebase on autopilot — one command, nine topics, fixes on a branch. |
| [**feature**](#feature) | `/plugin install feature@make-better` | Build each task in an isolated git-worktree workspace, ship it through a review gate into a PR, then merge it — four composable skills, all config-driven. |

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

> **Four composable skills: give a task its own working copy, ship it through a review gate into a PR, work the reviewer's comments, merge it.**

A [Claude Code](https://claude.com/claude-code) plugin that turns "build/fix X" into a disciplined,
reviewable flow. Each change is built in an isolated `git worktree` (deps symlinked, never
reinstalled), optionally runs on its own stable port behind a pretty `http://<task>.localhost` URL,
and lands in a PR — simplified, reviewed, committed and pushed **before** you ever see the report. A
live admin dashboard shows every workspace at a glance.

Config-driven, so it works for any single- or multi-repo workspace: **every policy is a key in
`.claude/feature/config.json`**, and everything a human reads is a **template you shadow** — no fork.

| Skill | Owns | Use it alone when |
|---|---|---|
| **`workspace`** | the environment: worktrees, dependency symlinks, copied env, ports, detached dev servers, proxy, reaper, dashboard state | you want an isolated running copy of the product for a task |
| **`ship`** | delivery: `/simplify` → review gate → commit → push → PR → report | "ship it" / "commit this" / "open a PR" on any branch |
| **`pr-feedback`** | the reviewer's comments: collect what's unaddressed, act on each, answer | "go through the PR comments" |
| **`merge`** | landing: sync base in, final review, green CI, merge, tear down | "merge it" on a branch with an open PR |

Only `workspace` enters a mode that persists for the session — and it stops the moment you say "no
workspace, just edit here". The other three are ordinary skills you can call on a plain repo.

## Install

```
/plugin marketplace add fivol/claude-make-better
/plugin install feature@make-better
```

## Quick start

1. Create a config at your workspace root — `<workspace-root>/.claude/feature/config.json` —
   declaring your repos:

   ```json
   {
     "repos": [
       { "name": "web", "base_branch": "main" }
     ]
   }
   ```

   The workspace root is the folder holding your repo checkouts (each a sibling folder named after
   its `name`); the config's presence marks that root. That is the whole minimum — it runs in `lite`
   mode: worktree, ship, PR, nothing to install beyond `git` and `gh`.

   Want the running app? Set `"mode": "full"` and give each repo a `port_band` and a `dev_start`, and
   every pass hands you `http://<task>.localhost`. Full schema — gates, `instructions`,
   `considerations`, env-copy, reaper, proxy — in
   **[configuration.md](docs/feature/configuration.md)**.

   Standing house rules go in `instructions` (an array of strings, workspace-wide or per repo) or in
   `.claude/feature/INSTRUCTIONS.md` — free-form markdown injected into every pass whenever the file
   exists, so you never restate the same rule per request. What the *report* contains is separate:
   drop a `.claude/feature/report.md` and it replaces the shipped default.

2. Just ask for a feature — "let's add a dark-mode toggle", "fix the upload limit". The agent enters
   Workspace Mode, creates the worktree(s), and from then on every pass is reviewed, committed and
   pushed into a PR automatically.

3. When you're happy, say "done" / "merge it" — the base branch is synced into the task branch (CI
   runs on the integrated code), the whole branch gets a final review, then it merges and cleans up.

## How it works

**Analyze** (preflight the toolchain, confirm scope) → **Init** (worktree, deps, and in full mode the
port, detached dev server and proxy) → **Build + ship** (`ship`: pick up PR comments → you implement →
`/simplify` → **review** → considerations → commit → push → PR → answer every comment → report with
deep test links) → **Merge** (`merge`: sync base, **final review of the integrated branch**, green CI,
merge per your strategy, clean up).

Comments you leave on the PR are part of that loop: `pr-feedback` picks up the unaddressed ones on the
next pass, does or argues with each, replies in the thread citing the fixing commit, and reports an
honest verdict per comment — see
**[PR review feedback](docs/feature/workflow.md#pr-review-feedback)**.

Before anything is committed it goes through the **review gate** — a blocking pass whose finders
never saw the conversation, hunting correctness bugs before cleanups, verifying each candidate before
believing it, and fixing what survives. You get a cleaned diff plus a one-line tally, not a list of
homework; the only thing that reaches the chat is what the reviewer refused to decide alone. Those
finders literally cannot edit your code (no `Edit`, no `Write` — fixing happens once, at the end),
each one reads its own angle from its own file, reasoning runs on Opus while retrieval runs on
Sonnet, and verification is batched and judges the evidence the finder quoted rather than searching
again. It runs again on the whole branch before the merge, where it is the only pass that ever sees
the conflict resolutions — and because that pass re-reviews everything at full depth, the per-pass
runs stay cheap by default.

All of it is yours to tune: **when** it fires (first pass, later ones, pre-merge — each switched
separately), **how hard**, **how many agents**, and **which angles** — including rewriting a built-in
angle for one project or adding your own. See **[the review gate](docs/feature/review.md)**.

## Docs

- **[The review gate](docs/feature/review.md)** — how the review works and how to tune it: the three
  passes and their run policy, levels and budgets, agent caps, the thirteen angles, and writing your
  own.
- **[Workflow & the four skills](docs/feature/workflow.md)** — the phases, the delivery contract, the
  standalone skills, PR review feedback, and the considerations checklist.
- **[Dashboard, URLs & commands](docs/feature/dashboard.md)** — the admin dashboard (`/feature-admin`),
  pretty `*.localhost` URLs, and the `/feature-doctor` preflight.
- **[Configuration](docs/feature/configuration.md)** — full config schema: `mode`, per-repo fields,
  the `simplify` / `commit` / `pr` / `merge` / `code_review` / `pr_feedback` policies, `instructions`
  + `INSTRUCTIONS.md`, `considerations`, the report templates, proxy, reaper caps, env overrides.

## Upgrading to 1.0

The skills were split and renamed, and policy moved into the config:

| Before | Now |
|---|---|
| `feature:feature` | `feature:workspace` |
| `feature:iteration` | `feature:ship` (PR comments → `feature:pr-feedback`, finish → `feature:merge`) |
| `--lite` flag, full by default | `mode` in the config, **`lite` by default** — set `"mode": "full"` to keep ports/servers/URLs |
| simplify/commit/PR/merge rules fixed in the skill | `simplify`, `commit`, `pr`, `merge` keys (defaults keep the old behaviour) |
| report format written into the skill | `.claude/feature/report.md` / `summary.md` templates |

`.claude/feature/config.json`, `.feature.json` and `/feature:review` are unchanged, so an existing
workspace keeps working — add `"mode": "full"` if you were relying on dev servers.

## Requirements

- Claude Code with plugin marketplace support
- `git` (with `git worktree`), `gh` (GitHub CLI, authenticated — for PRs)
- `python3` — used by the plugin's scripts
- macOS/Linux. Pretty URLs additionally need Caddy + Homebrew (optional)

## License

MIT
