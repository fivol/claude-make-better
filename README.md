# Make Better

Keep your codebase healthy on autopilot. A [Claude Code](https://claude.com/claude-code) plugin that continuously audits and improves an existing project — bugs, DRY, architecture, consistency, performance, tests, docs.

Most tools focus on building new things. **Make Better** is the opposite: it looks at what's already shipped and finds everything that's slightly broken, slightly inconsistent, slightly underdocumented, slightly wasteful — and fixes it. Run it on a schedule and the project quietly gets better between feature work.

## Install

```
/plugin marketplace add fivol/claude-make-better
/plugin install make-better@make-better
```

## Quick start

One command, that's it:

```
/make-better
```

It figures out the right thing to do based on the state of your repo:

- **No registry yet?** Discovers your subsystems first, then reviews them.
- **Registry getting stale?** Refreshes it incrementally, then reviews.
- **Registry fresh?** Goes straight to review.

You can pass arguments to control how many systems get reviewed and which area:

```
/make-better                  # smart defaults — usually 3 oldest systems
/make-better 8                # review 8 systems
/make-better flutter          # only systems under "flutter"
/make-better flutter 4        # 4 systems matching "flutter"
```

### Flags

- `--no-discover` — skip the discover phase, go straight to review (use when you've already discovered recently)
- `--rebuild` — force a full re-discovery before review (use after a major refactor)
- `--discover-only` — refresh the registry but don't review anything
- `--yes` (`-y`, `--auto`) — fully autonomous: no plan mode, no prompts, runs to completion. Required for cron / `/schedule`. See [Unattended runs](#unattended-runs--yes) below.

## What it actually does

### Phase 1: Discover (when needed)

Scans the repository and writes `docs/SYSTEMS.md` — a registry of every distinct **subsystem** (e.g. "Auth middleware", "Kanban drag-and-drop", "Image upload pipeline"). Each entry knows which folders it owns and when it was last reviewed.

Discovery only runs when the registry is missing or older than 30 days (configurable). Most invocations skip it.

### Phase 2: Review

Picks N stale systems from the registry and runs a structured audit on each one across nine topics:

- **bugs** — real defects in current code
- **completeness** — half-finished features, missing states, dead branches
- **dry** — duplicated logic to extract
- **architecture** — wrong-layer code, leaky abstractions, mis-placed responsibilities
- **consistency** — the same thing done two different ways across the codebase
- **efficiency** — obvious perf wins, wasted work
- **tests** — missing coverage where it actually matters
- **docs-sync** — drift between code and docs/contracts
- **security** *(optional)* — surface-level vulns

For each system it produces a plan, lets you review/edit/skip in plan mode, then applies fixes in **isolated git worktrees** in parallel — so concurrent reviews never step on each other or on your in-progress work. When fixes land, the system gets a fresh `last_review` stamp and won't be re-audited until it goes stale again (default: 14 days).

### Example output

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

Each finding lands as a separate, reviewable commit on a `systems-review/<system>` branch. Nothing is force-merged into your work — you decide what to integrate.

### Why this exists

A codebase rots in a thousand tiny ways no single PR review will catch: an enum gained a value but one switch was missed, a util got duplicated in three places, a doc went out of sync with the API, a test stopped covering anything meaningful. Make Better is a structured way to keep paying down that rot without making it your day job.

## Unattended runs (`--yes`)

By default, both phases pause for review — `/systems-discover` shows the proposed registry in plan mode, `/systems-review` shows a per-system plan and waits for approval. That's the right behavior when you're at the keyboard.

For cron, `/schedule`, and any other unattended use, pass `--yes`:

```
/make-better --yes 5
```

What changes:

- **Plan mode is skipped.** The agent runs the computed plan as-is.
- **Stale lockfiles are auto-removed** with a log line.
- **Ambiguous decisions don't block.** When the agent would normally ask a question, it picks the safe default if there is one. If there's no safe default, it **skips the affected system** (or proposal in discover) and lists it under `Skipped — human decision needed` in the final report.
- **Hard errors still abort.** Missing config, broken registry, no read access — these stop the run and surface as failures.

Fixes still land on isolated `systems-review/<system>` branches — nothing gets force-merged into your work. Read the branches and the skipped-systems list before merging anything.

## Set it and forget it

Pair `/make-better` with a schedule for hands-off maintenance:

```
/schedule create "0 9 * * 1" /make-better --yes 5
```

Every Monday at 9am: 5 stale systems reviewed, fixes proposed on branches, ready for your morning coffee.

## Configuration

Both skills read defaults from the installed plugin and merge in any project-local overrides at `<repo-root>/.claude/make-better.config.json`. Drop that file in your repo to customize without touching the plugin.

The skill itself runs `bash ${CLAUDE_SKILL_DIR}/bin/load-config.sh` (or `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/bin/load-config.sh` from a slash command) which prints the merged config as JSON — no need to think about merging yourself.

### Schema

```jsonc
{
  // Common keys
  "registry_path": "docs/SYSTEMS.md",
  "auto_discover_when_stale_days": 30,    // /make-better triggers refresh after this many days

  // /systems-review-specific overrides
  "review": {
    "user_language": "en",                 // language for user-facing messages (e.g. "ru", "es")
    "review_stale_after_days": 14,         // re-audit after this many days
    "default_systems_per_run": 3,
    "max_systems_per_run": 8,
    "max_parallel_review_agents": 4,
    "max_parallel_implement_agents": 2,
    "topic_agent_model": "sonnet",
    "review_agent_model": "opus",
    "implement_agent_model": "opus",
    "lockfile_dir": "docs",
    "branch_prefix": "systems-review",
    "topics_required": ["bugs", "completeness", "dry", "architecture", "consistency", "efficiency", "tests", "docs-sync"],
    "topics_optional": ["security"]
  },

  // /systems-discover-specific overrides
  "discover": {
    "max_parallel_scan_agents": 8,
    "scan_agent_model": "opus",
    "main_agent_model": "opus",
    "lockfile_path": "docs/.systems-discover.lock",
    "subsystem_detection": {
      "ignore_dirs": ["node_modules", "dist", "build", ".git", "coverage", ".next", "out", "target", "__pycache__"],
      "min_files_in_subsystem": 5
    },
    "doc_hint_paths": ["docs/AGENT_MAP", "docs/CONTRACTS", "docs/PRODUCT", "README.md"],
    "system_size_hints": {
      "typical_min_files": 1,
      "typical_max_files": 15,
      "split_threshold_files": 25
    }
  }
}
```

Every key is optional. Anything you don't specify falls back to the plugin's default. Nested objects (e.g. `subsystem_detection`) are deep-merged, so you can override one inner key without redeclaring the rest. Defaults live in `plugins/make-better/skills/<skill>/defaults.json` for reference.

### Common overrides

```jsonc
// Switch user-facing language to Russian
{ "review": { "user_language": "ru" } }

// Audit more aggressively
{ "review": { "review_stale_after_days": 7, "default_systems_per_run": 5 } }

// Don't auto-rediscover — only refresh when I explicitly run --rebuild
{ "auto_discover_when_stale_days": 99999 }

// Move the registry out of docs/
{ "registry_path": ".systems/registry.md" }

// Add a custom directory to ignore during discovery
{ "discover": { "subsystem_detection": { "ignore_dirs": ["node_modules", ".git", "vendor"] } } }
```

## Advanced: separate phases

`/make-better` covers the common case. For finer-grained control, the underlying commands are still available:

```
/systems-discover                 # incremental update of docs/SYSTEMS.md
/systems-discover --rebuild       # rewrite registry from scratch
/systems-discover flutter         # scoped to one area

/systems-review                   # default count, oldest first
/systems-review 8                 # review 8 systems
/systems-review flutter 4         # 4 systems matching "flutter"
```

Use these directly when you want explicit control over which phase runs.

## Updating

```
/plugin marketplace update make-better
/plugin update make-better@make-better
```

## Repo layout

```
claude-make-better/
├── .claude-plugin/
│   └── marketplace.json
└── plugins/
    └── make-better/
        ├── .claude-plugin/
        │   └── plugin.json
        ├── commands/
        │   └── make-better.md            ← /make-better orchestrator
        └── skills/
            ├── systems-discover/
            │   ├── SKILL.md
            │   ├── defaults.json
            │   ├── bin/
            │   │   ├── load-config.sh
            │   │   └── load-config.py
            │   └── prompts/
            └── systems-review/
                ├── SKILL.md
                ├── defaults.json
                ├── bin/
                │   ├── load-config.sh
                │   └── load-config.py
                ├── prompts/
                └── topics/
```

## Requirements

- Claude Code with plugin marketplace support
- `git`
- `python3` (or `python`) — used by the config loader; available on virtually every dev machine

## License

MIT
