# claude-skills

Collection of custom skills for [Claude Code](https://claude.com/claude-code), distributed as a plugin marketplace.

## Install

In Claude Code, add the marketplace and install the plugin:

```
/plugin marketplace add fivol/claude-skills
/plugin install main@fivol-skills
```

After install, skills become available with the `main:` prefix, e.g. `main:skill-name`.

## Make Better — keep your codebase healthy on autopilot

Two skills, one purpose: **continuously improve the codebase you already have**.

Most tools focus on building new things. `Make Better` is the opposite: it looks at what's already shipped and finds everything that's slightly broken, slightly inconsistent, slightly underdocumented, slightly wasteful — and fixes it. Run it on a schedule and the project quietly gets better between feature work.

It works in two steps:

### 1. `/systems-discover` — map the project

Scans the repository and writes `docs/SYSTEMS.md` — a registry of every distinct **subsystem** (e.g. "Auth middleware", "Kanban drag-and-drop", "Image upload pipeline"). Each entry knows which folders it owns and when it was last reviewed. Run it once to bootstrap, then re-run incrementally as the project grows.

```
/systems-discover                 # incremental update
/systems-discover --rebuild       # rewrite from scratch
/systems-discover flutter         # scoped to one area
```

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

A codebase rots in a thousand tiny ways no single PR review will catch: an enum gained a value but one switch was missed, a util got duplicated in three places, a doc went out of sync with the API, a test stopped covering anything meaningful. `Make Better` is a structured way to keep paying down that rot without making it your day job.

## Repo structure

```
claude-skills/
├── .claude-plugin/
│   └── marketplace.json        # marketplace catalog
└── plugins/
    └── main/
        ├── .claude-plugin/
        │   └── plugin.json     # plugin manifest
        └── skills/             # add SKILL.md files here
            └── <skill-name>/
                └── SKILL.md
```

## Adding a skill

1. Create `plugins/main/skills/<skill-name>/SKILL.md` with frontmatter:
   ```markdown
   ---
   name: skill-name
   description: When to use this skill (precise triggers)
   ---

   Skill body…
   ```
2. Commit and push. Users update with `/plugin update main@fivol-skills`.

## Updating

```
/plugin marketplace update fivol-skills
/plugin update main@fivol-skills
```
