# Angle Conventions · light

Find every rule that governs the changed code, then check the diff against it.

Where the rules live:

- `~/.claude/CLAUDE.md`
- the repo-root `CLAUDE.md` / `CLAUDE.local.md`
- any `CLAUDE.md` in a directory that is an ancestor of a changed file — a directory's file applies
  only at or below it
- the workspace's standing instructions, handed to you in the brief (`.claude/feature/INSTRUCTIONS.md`
  and the config's `instructions` / `repos[].instructions`, already assembled — do not re-derive them)

**Only flag a violation you can quote**: the exact rule and the exact line that breaks it. Name the
source file and quote the rule inside the finding, so the report can cite it.

No style preferences. No "spirit of the doc" inferences. Nothing applies ⇒ return nothing.
