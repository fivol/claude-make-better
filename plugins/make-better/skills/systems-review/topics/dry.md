---
name: dry
required: true
---

# DRY (Don't Repeat Yourself)

## What to look for

### 1. Duplicate logic blocks
- Functions or methods with near-identical implementations across different modules.
- Copy-pasted code blocks with minor variations (different variable names, slightly different params).
- Similar data transformation pipelines repeated in multiple places.

### 2. Repeated patterns without abstraction
- The same sequence of operations (fetch → transform → validate → store) repeated without a shared helper.
- Identical or near-identical component patterns (same hooks combo, same provider wiring, same render shape).
- Repeated conditional / switch‑case structures with the same shape and branch semantics.
- Repeated patterns of error mapping, formatting, or transformation that warrant a single helper.

### 3. Hardcoded values that should be constants/config
- Magic numbers or strings repeated across files.
- Configuration values scattered inline instead of centralized.
- Repeated default values that should be defined once.
- Inline regexes used for the same domain check in multiple places.

### 4. Missing utility extraction
- Inline logic that already exists in a utility function but is reimplemented.
- Helper functions duplicated across modules instead of being shared.
- Common operations (formatting, validation, normalization, parsing) reimplemented in multiple places.
- Multiple representations of the same data shape (parallel interfaces, divergent enums) that should be unified.

### 5. Redundant abstractions
- Multiple utility functions that do essentially the same thing under different names.
- Wrapper functions that add no value over what they wrap.
- Over-abstracted code where a simpler shared function would serve all callers.

## What NOT to look for
- Stylistic preferences (variable naming, brace style) → `consistency`.
- Logic bugs in the duplicates themselves → `bugs` (DRY only flags the duplication).
- Architectural layering → `architecture`.
- Performance of duplicated code → `efficiency`.

## Procedure
1. Skim each file in `areas:` for repeated patterns within the system.
2. Grep the rest of the codebase for similar logic that could be reused. Use semantically meaningful identifiers (function names, error messages, type shapes, repeated import combos).
3. Use globs to find files with similar names that often house duplicate logic (`*Client.ts`, `*Mapper.ts`, `*_helper.dart`).
4. Read suspicious files to confirm actual behavioral duplication — do not flag based on signature similarity alone. Compare function bodies.
5. For each finding, name the existing helper or proposed extraction point in `suggested_fix`.

## Operating rules
- **Threshold:** flag duplication only when it appears 3+ times, OR when 10+ lines are duplicated at least twice. Below the threshold, the cure (extraction, indirection) is usually worse than the disease.
- **Behavioral, not cosmetic:** two functions that look similar but do semantically distinct things are NOT a DRY violation. Note them as `low` severity at most, or skip entirely.
- **Closest sensible location:** when proposing extraction, prefer same module > shared utils > new module. Don't invent abstractions far from the call sites.
- **Don't over-abstract:** if extracting requires generic-fu, multiple flags, or an awkward signature to cover all callers, the original duplication may be cleaner. Skip.
- **Cross-system duplication:** if the system reimplements something that already lives in `common/`, `shared/`, another subsystem's utils, or the design system, name the canonical owner in `suggested_fix` and mark severity higher (the canonical version exists, this is pure waste).

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "lib/features/links/widgets/link_preview_sheet.dart",
  "line": 88,
  "issue": "url validation duplicates `lib/core/url/parse.dart::parseUrl` (3 call sites in this widget)",
  "severity": "medium",
  "suggested_fix": "replace inline regex with parseUrl(); remove local helper"
}
```

- `severity`:
  - `"high"` — large blocks duplicated, multiple call sites, OR canonical helper already exists elsewhere and the system ignored it.
  - `"medium"` — one duplicate of a non-trivial helper.
  - `"low"` — small repetition, low impact, or a borderline case worth noting but not urgent.
- For cross-system duplication, name the canonical owner in `suggested_fix`.

Return `[]` if nothing crosses the threshold. Do not invent findings.
