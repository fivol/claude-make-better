# Dashboard summary — the shipped default

Written to `<worktrees>/<task>/summary.md` in full mode, and rendered on the
task card by `/feature-admin`. Shadow it with `<root>/.claude/feature/summary.md`
or `report.summary_template` in `config.json`.

The dashboard renders **any** markdown — nothing below is parsed by structure.
The one mechanical convention: `- [ ]` items become click-persisted checkboxes,
so put things the reviewer ticks off there and nowhere else.

Overwrite the file each pass with the task's *current cumulative* state (not a
changelog of passes), in the user's language:

```markdown
# <task>

_updated <YYYY-MM-DD HH:MM> · pass <n> · <repos involved>_

## What's done
- <per-repo bullets of everything so far>
- simplify: ✓                                            # omit when the gate is off
- review: ✓ max — fixed 4 (P0 1) · skipped 1             # omit when the gate is off
- considerations: mobile ✓ · rtl n/a · cross-browser ⚠   # omit when the list is empty
- feedback: 5 · fixed 3 · answered 1 · deferred 1        # omit when nothing was picked up

## Review feedback        # whole section omitted when nothing was picked up
- <path:line> «<short quote>» → <verdict> · <what you did> (<sha>)

## Considerations / risks
- <cleaner approach, uncovered scenarios, edge cases, what's easy to forget>

## What to test
- [ ] <concrete check the reviewer clicks through>

## Links
- PR <repo>: <url>
- Test: http://<task>.<suffix>/<affected-route>
```
