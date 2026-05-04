---
name: tests
required: true
---

# Tests

## What to look for
- Coverage adequacy: does each meaningful behavior of the system have at least one test? Edge cases, error paths, state transitions.
- Right level: pure logic should be unit-tested (Vitest); multi-component flows should be integration; UI flows are E2E. A unit test mocking the universe is a smell.
- Realism: assertions match how the code is actually used (right inputs, right expected outputs, right error types). No "tests-for-tests-sake" that re-implement the function.
- Staleness: tests that pass but no longer reflect current behavior (asserting on a removed field, mocking a removed dependency).
- Brittleness: tests that fail under reasonable refactoring even though behavior is preserved.

## What NOT to look for
- Bugs in the production code itself → `bugs`.
- Test code style nits → `consistency`.

## Procedure
1. Locate tests covering files in `areas:` (under `tests/`, `server/tests/`, `bot/tests/`, sibling `*_test.dart` for Flutter).
2. **Run** the located tests:
   - Node code → `pnpm test <path>` or the project-specific test command.
   - Flutter code → `cd app && flutter test <path>`.
   - Server code → `cd server && pnpm test <path>`.
3. Record failures with their messages.
4. For each behavior in the production code that lacks a test, propose one (with a one-line description; the implementer writes the actual code).

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "tests/unit/auth/error-mapping.test.ts",
  "line": 12,
  "issue": "asserts on response.error.code which was removed in a previous refactor; test passes by accident",
  "severity": "high",
  "suggested_fix": "update assertion to check response.errorMessage"
}
```

For missing coverage:

```json
{
  "file": "tests/unit/auth/error-mapping.test.ts",
  "line": 0,
  "issue": "no test for 401 → toast mapping",
  "severity": "medium",
  "suggested_fix": "add test: given 401 response, error mapper returns ToastError with localized title"
}
```

- `severity`: `"high"` (test broken or missing for critical behavior) | `"medium"` (gap in non-critical behavior) | `"low"` (style).

Return `[]` if all tests are present, current, and passing.
