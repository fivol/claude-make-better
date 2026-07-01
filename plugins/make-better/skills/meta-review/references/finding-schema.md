# Schemas

## Finding (what each subagent returns)

A subagent returns a **JSON array** of these objects (and nothing else):

```json
{
  "lens": "A",                          // A|B|C|D|E (which lens produced it)
  "title": "Re-runs failed deploy without checking check_pushed",
  "severity": "important",              // important | significant | minor
  "category": "workflow",               // free-form theme tag
  "summary": "Across sessions the deploy is retried verbatim after failing on uncommitted changes, instead of committing first.",
  "evidence": [
    {"session_id": "ac939aa9-…", "ref": "turn ~40, Bash `make deploy-dev`", "quote": "check_pushed: uncommitted changes"}
  ],
  "occurrences": 3,                     // how many times / sessions it recurred
  "recommendation": "Add a pre-deploy step that commits or aborts; or a hook that blocks deploy on a dirty tree.",
  "effort": "small",                    // small | medium | large
  "proposed_change": "Optional: concrete edit / new skill / hook shape."
}
```

Severity rubric (subagents rate, orchestrator re-ranks):
- **important** — recurring and costly: wastes real time, breaks things, or
  violates an explicit rule. Fix soon.
- **significant** — a real improvement worth doing, not urgent.
- **minor** — small polish / nice-to-have / low effort.

## Session record (one JSONL line per run, appended via `meta_review.py record`)

```json
{
  "schema": "meta-review/v1",
  "reviewed_at": "2026-06-09T15:40:00Z",   // = window.until; next run's `since`
  "window": {"since": "2026-06-02T00:00:00Z", "until": "2026-06-09T15:40:00Z"},
  "scope": {"mode": "project", "project_dirs": ["/Users/…/-Users-…-itsai"]},
  "sessions_analyzed": 22,
  "findings": [ /* the merged, re-ranked findings (array of the objects above) */ ],
  "decisions": [
    {
      "title": "Re-runs failed deploy without checking check_pushed",
      "severity": "important",
      "action": "applied",               // applied | deferred | dismissed | noted
      "note": "Added pre-deploy guard hook to settings.json",
      "artifact": "~/.claude/settings.json"   // file/skill/PR touched, if any
    }
  ],
  "stats": {"by_severity": {"important": 2, "significant": 4, "minor": 3}}
}
```

Notes:
- `reviewed_at` MUST equal `window.until` — it's what the next run reads as
  `since`, so the windows tessellate without gaps or overlap.
- Every finding gets exactly one entry in `decisions` (even `noted`/`dismissed`)
  so the log is a complete record of what was decided.
- `deferred` decisions resurface as `open_items` in the next run's `plan`.
- The helper fills `schema`, `reviewed_at` (if absent), `findings`, `decisions`
  defaults — but pass them explicitly; rely on defaults only as a safety net.
