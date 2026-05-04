# Make Better

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

Claude Code has no `/plugin update` subcommand — refresh the catalog, then reinstall:

```
/plugin marketplace update make-better
/plugin uninstall make-better@make-better
/plugin install make-better@make-better
```

Or open the interactive UI with bare `/plugin` and manage from the **Installed** tab.

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

## License

MIT
