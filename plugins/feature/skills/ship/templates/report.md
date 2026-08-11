# Chat report — the shipped default

Shadow this file to change what a pass reports, without forking the skill:

- `<root>/.claude/feature/report.md` — same shape, your blocks;
- or `report.chat_template` in `config.json`, pointing anywhere under the root.

Blocks in this order, **ending with the test links** so they're the last thing
the user can click. A block with nothing to say is omitted entirely — an empty
heading is noise.

1. **What's done** — concise per-repo summary of this pass. End with the status
   lines that apply: `simplify: ✓` / `simplify: skipped (minor)` / omitted when
   the gate is off · `review: ✓ max — fixed 4 (P0 1) · skipped 1` ·
   `considerations: mobile ✓ · rtl n/a · cross-browser ⚠` (only when the config
   list is non-empty) · `feedback: 5 · fixed 3 · answered 1 · deferred 1` (only
   when comments were picked up).
2. **Review feedback** — one bullet per PR comment you picked up, each carrying
   three things: **where** (`path:line` + a short quote), **your honest
   verdict**, and **what you actually did**. The verdict is the point: agreed ·
   disagreed, with the argument · there's a better option, namely … · what's
   there is justified, because … Agreeing with everything is a smell, not
   politeness.
3. **Needs you** — only for items the review gate could not decide alone. One
   numbered question each: where it is, what was found, and the two or more
   defensible options. A dropped item here is a defect nobody ever saw.
4. **Considerations** — tied to this change: a cleaner/more correct approach,
   scenarios still uncovered, edge cases, what's easy to forget (errors,
   empty/limit states, mobile, i18n, migrations, auth).
5. **🔗 Test / verify** — LAST.
   - *full mode:* clickable deep links to exactly the affected page(s)/endpoint(s)
     — `http://<task>.<suffix>/<route>` (+ the `http://localhost:<port>/…`
     fallback) — API URLs for backend changes, then the PR link(s).
   - *lite mode:* no app URLs — how to verify (typecheck / build / the key diff
     lines) + the PR link(s).

Write it in the user's language (`output_language`). Prose and headings only —
how the text is *rendered* (markdown in a terminal, HTML in a chat integration)
belongs to whatever is running this skill, not here.
