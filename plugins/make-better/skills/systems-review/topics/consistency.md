---
name: consistency
required: true
---

# Consistency

## What to look for
- Naming conventions: identifiers that drift from how the rest of the codebase names similar things (e.g., `userId` vs `user_id`, `getNode` vs `fetchNode`).
- Error handling style: `try/catch` patterns, error types, log call shapes — should match the project's prevailing style.
- Use of shared utilities: places that hand-roll logic where a project-wide helper exists (`common/`, design tokens, `i18n` keys, `lib/design`).
- Type conventions: shape of result/error envelopes, optional vs nullable, branded types.
- File and module structure: where similar concerns live elsewhere should match where this system places them.
- Comment and doc style: matches the surrounding tone, density, and language (English).

## What NOT to look for
- Whether the patterns themselves are good → `architecture`.
- Whether code is duplicated → `dry`.
- Logic correctness → `bugs`.

## Procedure
1. Pick 1–2 reference subsystems of similar shape (e.g., another route handler, another widget tree).
2. Compare naming, error handling, and util usage against the system under review.
3. Flag every divergence that adds friction for a reader who already knows the rest of the codebase.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "src/client/auth_client.ts",
  "line": 22,
  "issue": "uses `userId`; rest of codebase (src/routes/auth.ts:14, src/api/users.ts:9) uses `accountId`",
  "severity": "low",
  "suggested_fix": "rename to `accountId` for consistency"
}
```

- `severity`: `"medium"` for style drifts that obscure intent across the codebase | `"low"` for purely cosmetic drift.
- Include reference paths in `issue` so the implementer can verify.

Return `[]` if nothing is found.
