# Configuration reference

Make Better reads built-in defaults from the installed plugin and merges in any project-local overrides. Drop a JSON file at `<repo-root>/.claude/make-better/config.json` to customize anything.

## File layout

```
<repo>/.claude/
└── make-better/
    ├── config.json              # this file
    └── topics/                  # optional — see custom-topics.md
        └── *.md
```

## Schema

Every key is optional. Anything missing falls back to the plugin's default. Nested objects (e.g. `subsystem_detection`) are deep-merged — you can override one inner key without redeclaring the rest.

```jsonc
{
  // -------- Common (apply to both skills) --------
  "registry_path": "docs/SYSTEMS.md",
  "auto_discover_when_stale_days": 30,    // /make-better triggers a refresh after this many days

  // -------- /systems-review-specific --------
  "review": {
    "user_language": "en",                // language for every user-facing message ("ru", "es", etc.)
    "review_stale_after_days": 14,        // re-audit a system after this many days

    "default_systems_per_run": 3,         // count when not specified
    "max_systems_per_run": 8,             // upper bound; user-supplied counts get clamped

    "max_parallel_review_agents": 4,      // review-agents in parallel
    "max_parallel_implement_agents": 2,   // implement-agents in parallel

    "topic_agent_model": "sonnet",        // per-topic auditor
    "review_agent_model": "opus",         // per-system planner
    "implement_agent_model": "opus",      // applies fixes inside worktrees

    "lockfile_dir": "docs",
    "stale_lockfile_after_hours": 3,
    "branch_prefix": "systems-review",

    "topics_required": [                  // always run on every system
      "bugs", "completeness", "dry", "architecture",
      "consistency", "efficiency", "tests", "docs-sync"
    ],
    "topics_optional": ["security"]       // run when applicable
  },

  // -------- /systems-discover-specific --------
  "discover": {
    "max_parallel_scan_agents": 8,
    "scan_agent_model": "opus",
    "main_agent_model": "opus",

    "lockfile_path": "docs/.systems-discover.lock",

    "subsystem_detection": {
      "ignore_dirs": [
        "node_modules", "dist", "build", ".git", "coverage",
        ".next", "out", "target", "__pycache__"
      ],
      "min_files_in_subsystem": 5
    },

    "doc_hint_paths": [
      "docs/AGENT_MAP", "docs/CONTRACTS", "docs/PRODUCT", "README.md"
    ],

    "system_size_hints": {
      "typical_min_files": 1,
      "typical_max_files": 15,
      "split_threshold_files": 25         // split a proposal into multiple systems above this
    }
  }
}
```

## Common overrides

```jsonc
// Switch to Russian
{ "review": { "user_language": "ru" } }
```

```jsonc
// Audit more aggressively
{
  "review": {
    "review_stale_after_days": 7,
    "default_systems_per_run": 5
  }
}
```

```jsonc
// Don't auto-rediscover. /make-better always goes straight to review.
{ "auto_discover_when_stale_days": 99999 }
```

```jsonc
// Move the registry out of docs/
{ "registry_path": ".systems/registry.md" }
```

```jsonc
// Add a custom ignore dir for discovery
{
  "discover": {
    "subsystem_detection": {
      "ignore_dirs": [
        "node_modules", "dist", "build", ".git",
        "coverage", ".next", "out", "target", "__pycache__",
        "vendor", "third_party"
      ]
    }
  }
}
```

```jsonc
// Add a custom review topic — see docs/custom-topics.md
{
  "review": {
    "topics_required": [
      "bugs", "completeness", "dry", "architecture",
      "consistency", "efficiency", "tests", "docs-sync",
      "perf-budget"                       // your custom topic
    ]
  }
}
```

## How merging works

Three layers, in order from lowest to highest precedence:

1. **Plugin defaults** — `plugins/make-better/skills/<skill>/defaults.json`. Ship with the plugin.
2. **Common keys in your config** — top-level keys (e.g. `registry_path`) apply to both skills.
3. **Section keys in your config** — `review:` keys override for `/systems-review`, `discover:` keys override for `/systems-discover`.

The merge is **deep** for objects (you can override one key inside `subsystem_detection` without redeclaring the rest) and **replace** for arrays (your `topics_required` fully replaces the default — list every topic you want, including built-ins you keep).

## Inspecting the merged result

If your override doesn't seem to apply, run the loader directly:

```bash
# Find the installed plugin's loader and run it from your repo root.
cd /path/to/your/repo
bash $(find ~/.claude/plugins -path "*/make-better/skills/systems-review/bin/load-config.sh" | head -1)
```

It prints the merged JSON. The `_meta` section tells you whether your override file was found and where it was looked for:

```json
"_meta": {
  "skill": "review",
  "defaults_path": "/path/to/plugin/.../defaults.json",
  "override_path": "/your/repo/.claude/make-better/config.json",
  "override_applied": true,
  "user_topics_dir": "/your/repo/.claude/make-better/topics",
  "plugin_topics_dir": "/path/to/plugin/.../topics",
  "repo_root": "/your/repo"
}
```

If `override_applied: false`, the file isn't where the loader expects it. Check the path in `override_path`.
