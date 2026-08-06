# Angle B — removed-behavior auditor · deep

For every line the diff DELETES or replaces, name the invariant or behavior it enforced, then search
the new code for where that invariant is re-established. If you cannot find it, that is a candidate.

What to look for:

- a removed guard or early return
- a dropped error path — a `catch`, a status code, a fallback
- a validation narrowed: a stricter type replaced by a looser one, a check moved behind a flag
- a deleted test that covered a real case, or an assertion weakened to keep it green
- a constant, default or floor removed with no replacement

The failure scenario is **what now reaches the code the removed line used to stop**. Name it
concretely — the input or state that gets through, and what it breaks when it does.
