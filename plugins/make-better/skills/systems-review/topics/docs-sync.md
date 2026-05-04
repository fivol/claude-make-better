---
name: docs-sync
required: true
---

# Docs sync

## What to look for
- README and `docs/` references to behavior that no longer exists (renamed flag, removed endpoint).
- Public API contracts in `docs/CONTRACTS/` that don't match the actual exports/types/handlers.
- `docs/AGENT_MAP/` entries that point to moved or deleted files.
- Comments above functions that describe stale parameters, removed return shapes, or wrong invariants.
- Missing docs for behavior that is reasonably user-visible (CLI flags, config keys, externally-shaped errors).

## What NOT to look for
- Style of prose → leave alone.
- Outdated docs in unrelated subsystems.

## Procedure
1. List all docs that mention the system: `grep` for system name and key file names in `docs/`, `README.md`, top-of-file comments under `areas:`.
2. Compare statements against current code.
3. Flag mismatches and missing entries that the system clearly warrants.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "docs/CONTRACTS/firebase.md",
  "line": 142,
  "issue": "documents POST /api/databases returning {id, name}; current handler returns {databaseId, name, createdAt}",
  "severity": "medium",
  "suggested_fix": "update doc to match current handler shape"
}
```

For missing docs:

```json
{
  "file": "docs/AGENT_MAP/backend.md",
  "line": 0,
  "issue": "Snapshot Merger added in this system has no entry under Internal Structure",
  "severity": "low",
  "suggested_fix": "add module row pointing to src/services/payment_processor.ts"
}
```

Return `[]` if docs are in sync.
