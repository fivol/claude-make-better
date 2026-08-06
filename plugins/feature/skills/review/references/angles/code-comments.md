# Angle Code comments — does the change honour what the code asks for · light · level `max`

Read the comments and docstrings in and around the changed regions: `NOTE:`, `HACK:`, `TODO:`,
"keep in sync with…", "must run before…", "do not call directly", invariant notes above a function,
and the rationale comments that explain why a value is the value it is.

Two kinds of finding, both real:

1. **The change violates a comment** — it calls the thing the comment says not to call, breaks the
   ordering the comment requires, or drifts from the file the comment says to keep in sync.
2. **The change invalidates a comment** — the comment is now a lie. A comment explaining a mechanism
   the diff removed is exactly this, and its fix is usually one line.

Quote the comment and the line that contradicts it. A comment that was already wrong before this
diff is out of scope.
