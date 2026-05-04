# Make Better

Keep your codebase healthy on autopilot. A [Claude Code](https://claude.com/claude-code) plugin that continuously audits and improves an existing project — bugs, DRY, architecture, consistency, performance, tests, docs.

Most tools focus on building new things. **Make Better** is the opposite: it looks at what's already shipped and finds everything that's slightly broken, slightly inconsistent, slightly underdocumented, slightly wasteful — and fixes it. Run it on a schedule and the project quietly gets better between feature work.

## Install

```
/plugin marketplace add fivol/claude-make-better
/plugin install make-better@make-better
```

After install, two slash commands become available: `/systems-discover` and `/systems-review`.

## How it works

### 1. `/systems-discover` — map the project

Scans the repository and writes `docs/SYSTEMS.md` — a registry of every distinct **subsystem** (e.g. "Auth middleware", "Kanban drag-and-drop", "Image upload pipeline"). Each entry knows which folders it owns and when it was last reviewed.

```
/systems-discover                 # incremental update
/systems-discover --rebuild       # rewrite from scratch
/systems-discover flutter         # scoped to one area
```

Run it once to bootstrap, then re-run incrementally as the project grows.

### 2. `/systems-review` — audit and fix

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

```
/systems-review                   # default count, oldest first
/systems-review 8                 # review 8 systems
/systems-review flutter 4         # 4 systems matching "flutter"
```

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

## Configuration

Both skills read defaults from the installed plugin and merge in any project-local overrides at `<repo-root>/.claude/make-better.config.json`. Drop that file in your repo to customize without touching the plugin.

The skill itself runs `bash ${CLAUDE_SKILL_DIR}/bin/load-config.sh` which prints the merged config as JSON — no need to think about merging yourself.

### Schema

```jsonc
{
  // Common keys (apply to both skills)
  "registry_path": "docs/SYSTEMS.md",

  // systems-review-specific overrides
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

  // systems-discover-specific overrides
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

// Move the registry out of docs/
{ "registry_path": ".systems/registry.md" }

// Add a custom directory to ignore during discovery
{ "discover": { "subsystem_detection": { "ignore_dirs": ["node_modules", ".git", "vendor"] } } }
```

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
