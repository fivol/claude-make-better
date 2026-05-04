---
name: efficiency
required: true
---

# Efficiency

## What to look for
- N+1 queries or sequential awaits where parallelism is safe.
- Suboptimal data structures (linear scans where a `Map`/`Set` would be O(1); rebuilding lookup tables in a hot loop).
- Redundant rebuilds: in Flutter — unnecessary widget rebuilds via missing `const`, broad `setState`, listening to oversized providers; in React — re-renders due to inline objects/functions.
- Redundant network calls: not deduping, not caching short-lived results, not batching.
- Heavy work on the main thread / UI thread: synchronous parsing, large JSON.parse on hot paths, image decoding without isolation.
- Memory: large arrays kept after use, accidental references preventing GC.

## What NOT to look for
- Low-impact micro-optimization in cold paths.
- Logic bugs that happen to be slow → `bugs`.
- Architectural reasons code is slow → `architecture`.

## Procedure
1. Identify hot paths in the system (request handlers, render trees, frequent event handlers).
2. Look at loops and awaits in those paths first.
3. Check for repeated work between calls that could be cached.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "src/routes/checkout.ts",
  "line": 88,
  "issue": "for each patch, fetches user record sequentially (N+1)",
  "severity": "medium",
  "suggested_fix": "load all users in one query before the loop"
}
```

- `severity`: `"high"` (measurable user-visible cost) | `"medium"` (clear waste in a hot path) | `"low"` (theoretical, low impact).

Return `[]` if nothing is found.
