---
name: architecture
required: true
---

# Architecture

## What to look for
- Boundary violations: code in one layer reaching into the internals of another (e.g., a UI widget directly mutating database state, a service importing from `lib/widgets/`).
- Single-responsibility violations: a file or class doing several unrelated things; functions that grow past one clear purpose.
- Leaked internals: types or helpers exported only for testing, indirect coupling through global state, hidden side effects.
- Mixed abstraction levels in the same module (low-level byte handling next to high-level orchestration).
- Missing seams: pieces that should be replaceable (e.g., a transport layer, a serializer) but are wired in directly.
- Public contracts that don't match how the system is actually used.

## What NOT to look for
- Performance → `efficiency`.
- Logic bugs → `bugs`.
- Repeated code → `dry`.
- Naming conventions → `consistency`.

## Procedure
1. Identify the system's intended layers (UI / domain / persistence / IO; or controller / service / repository — adapt to the codebase).
2. Trace each `areas:` file to a layer.
3. Note imports that cross layers in the wrong direction.
4. Look at file sizes and exported surface; large files with broad exports are a smell.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "server/src/services/Database.ts",
  "line": 0,
  "issue": "Database service directly imports HTTP response builder from routes/auth.ts",
  "severity": "high",
  "suggested_fix": "lift response shaping into the route layer; service returns plain data"
}
```

- `severity`: `"high"` (cross-layer leak with growing impact) | `"medium"` (single boundary smudge) | `"low"` (cosmetic boundary issue).
- `line: 0` is acceptable for file-level issues.

Return `[]` if nothing is found.
