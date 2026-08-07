# Angle C — cross-file tracer · deep

For each function, export, endpoint or config key the diff changes, `Grep` for its callers and check
whether the change breaks any call site:

- a new precondition the caller doesn't satisfy
- a changed return shape or nullability
- a new exception or error branch the caller doesn't handle
- a timing or ordering dependency — must run after X, must not run twice, must not run concurrently

Also check callees: does a parallel change elsewhere in the same diff make an existing call unsafe?

Cap your searches (`| head -50`, `-l` when you only need the file list) and stay inside the repo's
source directory. **A caller you found and quoted is a finding; a caller you assume exists is not.**
