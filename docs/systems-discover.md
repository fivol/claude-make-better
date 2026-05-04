# How `/systems-discover` works

`/systems-discover` builds and maintains `docs/SYSTEMS.md` — the registry of subsystems that `/systems-review` audits. This document explains its phases. For user-facing usage, see the [README](../README.md).

## What's a "system"?

A **system** is a coherent unit of behavior, typically 1–15 files: an auth middleware, a kanban drag-and-drop layer, an image upload pipeline, a payment retry loop. Systems are smaller than a "module" or a "package" — they're the level at which a focused review makes sense.

Systems are grouped into **sections** (e.g. "Server / API", "Flutter App / Sync", "Bot / Commands"). Sections roughly mirror top-level directories or logical areas of the project.

## Inputs

```
/systems-discover [<area>] [--rebuild] [--yes]
```

- `<area>` — restrict scanning to a specific subsystem (e.g. `flutter`, `server/auth`). Empty = full repo.
- `--rebuild` — rewrite from scratch, ignoring the existing registry.
- `--yes` — non-interactive mode (skips plan mode, auto-resolves prompts).

Default mode is **incremental**: only files changed since the last sweep (per section) plus files not yet mapped to any system are reconsidered.

## Phases

### Phase 0 — Bootstrap

1. **Acquire lockfile** at `docs/.systems-discover.lock`. If a recent one exists from a live peer, refuse to start. With `--yes`, stale lockfiles auto-clear.
2. **Read existing registry** at `<registry_path>`. Parses YAML frontmatter (`last_discovered_by_section: { <section>: <iso date> }`) and the body (sections, systems, areas, notes).

### Phase 1 — Detect subsystems

Walks top-level directories, applying `subsystem_detection.ignore_dirs` (default: `node_modules`, `dist`, `.git`, etc.). A subsystem is any directory with at least `min_files_in_subsystem` (default 5) files. Each becomes a parallel scan target.

If `<area>` is set, only matching subsystems are scanned.

### Phase 2 — Scan (parallel)

Dispatches one **scan agent** per subsystem (`max_parallel_scan_agents`, default 8). Each scan agent:

1. Reads relevant doc hints (`doc_hint_paths` — default `docs/AGENT_MAP/`, `docs/CONTRACTS/`, `docs/PRODUCT/`, the subsystem's own README).
2. In incremental mode: only considers files changed in git since `last_discovered_by_section[<this section>]` plus files not currently mapped to any existing system. In rebuild mode: every file under the root.
3. Proposes systems with `{ name, areas, notes, preserved_from_existing? }`. Each system targets `system_size_hints` (default 1–15 files; split if >25).
4. Returns structured JSON: `{ subsystem, proposed_new, areas_patches, notes_appends, covered_existing }`.

### Phase 3 — Cross-cutting merge

The main agent collects all scan-agent outputs and reconciles cross-cutting systems (a system whose areas span multiple subsystems — e.g. an "Auth flow" that spans both server-side handlers and client-side login UI).

For each potential cross-cutting system:

- Same name proposed by multiple scan agents → merge into one entry, union the `areas:`.
- Subset relationship (one scan's proposal is a strict subset of another's) → keep the bigger one.
- Renames (a `--rebuild` proposal with no name match but ≥80% area overlap with an existing system) → flag in plan mode as `<new name> (renamed from <old name>)` so the user explicitly approves losing review history.
- Conflicts that the merger can't resolve → `AskUserQuestion`. With `--yes` and no safe default, the affected proposal is skipped and reported.

### Phase 4 — Plan mode

Renders the proposed registry as a markdown document and shows it for approval. The user can:

- Approve as-is — proceeds to Phase 5.
- Inspect (`show <system>` / `show areas`) — print details, stay in plan mode.
- Edit ("split this system in two", "merge X and Y", "rename X", "drop Z") — main agent applies the edit and re-shows.
- Cancel — exits without writing.

With `--yes`, this phase is skipped.

### Phase 5 — Write

Writes `<registry_path>` with:

- Frontmatter: updated `last_discovered_by_section` — every section that was swept gets today's date.
- Body: section by section, system by system. Existing systems' `last_review`, `status`, and `blocker` fields are **preserved** unless the system was renamed (in which case the user explicitly approved losing them in plan mode).

Lockfile released.

## Registry format

```markdown
---
last_discovered_by_section:
  Server / API: 2026-04-29
  Flutter App / Sync: 2026-04-15
---

# Systems Registry

Systems registry for automated review (`/systems-review`).
Maintained by humans + `/systems-discover` + `/systems-review`.

## Server / API

### Auth middleware
- areas:
  - src/middleware/auth.ts
  - src/services/session.ts
- last_review: 2026-04-29
- notes: handles JWT verification and session lookup

### Payment Processor ⚠ needs decision
- areas:
  - src/services/payment_processor.ts
- status: needs_user_decision
- blocker: "retry strategy unclear — exponential vs jittered backoff under load"
- notes: …
```

The format is human-editable. Hand-edits survive `/systems-discover` runs as long as system names match.

## Concurrency

| Layer | Limit | Notes |
|---|---|---|
| Scan agents | `max_parallel_scan_agents` (default 8) | one per top-level subsystem |
| Cross-cutting merge | sequential | runs in main agent after all scans return |

Only one `/systems-discover` may run at a time per repo (lockfile enforces it). Concurrent reviews are fine because review only reads the registry.

## Non-interactive behavior (`--yes`)

| Decision point | Default behavior | `--yes` behavior |
|---|---|---|
| Plan mode (Phase 4) | wait for approval | skip, write directly |
| Stale lockfile | prompt | auto-remove with log line |
| Cross-cutting merge ambiguity | AskUserQuestion | safe default if available, else skip the proposal and log it |
| Rename detection | AskUserQuestion | safe default = treat as new system (preserves the old entry's review history under its old name) |
| Hard error | abort | abort |

## Config knobs

Full reference: [configuration.md](configuration.md). Specific to discover:

- `max_parallel_scan_agents` (8).
- `scan_agent_model` (opus) / `main_agent_model` (opus).
- `lockfile_path` (`docs/.systems-discover.lock`).
- `subsystem_detection.ignore_dirs` / `subsystem_detection.min_files_in_subsystem`.
- `doc_hint_paths`.
- `system_size_hints.{typical_min_files, typical_max_files, split_threshold_files}`.
