# Angle Reuse · light

Flag new code that re-implements something the codebase already has.

Grep the shared/utility modules and the files adjacent to the change, then **name the existing helper
to call instead**. A reuse finding without the replacement named is not actionable and must not be
reported.

Check both directions:

- a new helper that duplicates one that already exists;
- a copy-pasted block that should have called a helper that already exists.

Pattern-level duplication counts when the existing code solves the **same problem** — say which file
solves it and how. Two functions that merely look alike but answer different questions are not a
finding.
