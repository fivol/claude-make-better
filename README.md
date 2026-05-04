# Make Better

A [Claude Code](https://claude.com/claude-code) plugin that audits and improves an existing codebase. One command picks the oldest subsystems of your project and reviews them across nine topics — bugs, DRY, architecture, consistency, efficiency, tests, docs sync, completeness, and (optionally) security. Fixes are applied as merge commits on your current branch — never pushed, easy to inspect or undo.

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

```
/schedule create "0 9 * * 1" /make-better --yes 5
```

Every Monday at 9am: 5 stale systems reviewed, fixes merged into the current branch (unpushed), ready for your morning coffee.

## Configuration

Drop a JSON file at `<repo-root>/.claude/make-better/config.json` to customize without touching the plugin:

```jsonc
{
  "review": {
    "user_language": "ru",                 // user-facing messages in Russian
    "review_stale_after_days": 7,          // re-audit weekly instead of bi-weekly
    "default_systems_per_run": 5
  },
  "discover": {
    "subsystem_detection": {
      "ignore_dirs": ["node_modules", ".git", "vendor"]
    }
  }
}
```

Every key is optional. Anything missing falls back to plugin defaults. Full schema and all knobs: **[docs/configuration.md](docs/configuration.md)**.

## Custom review topics

Add your own audit topics — perf budgets, accessibility, internal style guides, anything you want flagged on every review.

1. Drop a prompt at `.claude/make-better/topics/<name>.md`.
2. Add `<name>` to `topics_required` in your config.

Done. Full guide with prompt template: **[docs/custom-topics.md](docs/custom-topics.md)**.

## Updating

```
/plugin marketplace update make-better
/plugin update make-better@make-better
```

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

## License

MIT
