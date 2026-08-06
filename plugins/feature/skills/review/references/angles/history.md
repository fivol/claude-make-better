# Angle History — what the code's past says · light

```bash
git -C "$WT" log -L <start>,<end>:<file> | head -200
git -C "$WT" blame -L <start>,<end> -- <file>
```

You are looking for a change that **re-breaks something already fixed**:

- a guard added by an earlier bugfix and now removed
- a value re-hardcoded that was made configurable on purpose
- a workaround deleted whose reason still holds
- a constant changed back to what it was before a commit that deliberately changed it

**Cite the commit that established the behavior** — sha, date and subject line. A history finding
without that citation is a guess, and the caller cannot act on it.

Cap the log output. `log -L` on a long-lived file can print thousands of lines; you need the commits
that touched *these* lines, not the file's biography.
