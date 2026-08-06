# Angle A — line-by-line diff scan · deep

Read every hunk in the pack, line by line. Then `Read` the enclosing function for each hunk — bugs in
unchanged lines of a touched function are in scope, because the change either re-exposes them or
fails to fix them.

For every line ask: what input, state, timing or platform makes this line wrong?

- inverted or wrong conditions; off-by-one on a boundary the code doesn't exclude
- null/undefined deref; falsy-zero or empty-string treated as missing
- a missing `await`, a promise created and never awaited
- wrong-variable copy-paste — the tell is two adjacent lines that differ by one identifier
- an error swallowed in a `catch` that should propagate
- unescaped regex metacharacters; an anchor lost from a pattern or an allowlist

Report one candidate per distinct mechanism. Two lines wrong for the same reason are one candidate;
one line wrong for two reasons is two.
