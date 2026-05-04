---
name: bugs
required: true
---

# Bugs

## What to look for
- Logic errors: wrong branches, inverted conditions, off-by-one, wrong order of operations.
- Edge cases: empty arrays, null/undefined, negative numbers, Unicode, boundary dates, expired tokens.
- Race conditions: shared mutations without synchronization, await ordering bugs, missing cancellation on long-running operations.
- Mishandled errors: swallowed exceptions, lost stack traces, errors caught at one layer that mask issues at another.
- Resource leaks: unclosed WebSockets, unsubscribed listeners, uncleaned timers.
- State inconsistencies: partial updates left after a failure path, stale cache after invalidation, optimistic UI not rolled back on error.

## What NOT to look for
- Style nits → `consistency`.
- Performance → `efficiency`.
- Duplication → `dry`.
- Architectural concerns → `architecture`.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "src/services/database.ts",
  "line": 142,
  "issue": "session token written to logs in error path",
  "severity": "high",
  "suggested_fix": "redact session field before logger.error"
}
```

- `severity`: `"high"` | `"medium"` | `"low"`.
- `line` may be omitted if the issue spans the file as a whole.
- `suggested_fix` must be concrete enough to implement without further investigation.

Return `[]` if nothing is found. Do not invent findings to fill space.
