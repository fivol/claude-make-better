# Review lenses

Five focused perspectives. Spawn one subagent per lens. Each subagent gets the
**shared context block** (below) + its **lens brief** + the finding schema, and
returns a JSON array of findings.

Keep the lenses distinct so they don't all report the same thing — though some
overlap is expected and useful (cross-lens agreement = a strong signal; you'll
merge those when aggregating).

---

## Shared context block (prepend to every subagent prompt)

```
You are a meta-review subagent auditing the user's own Claude Code session
history. Your final message IS the result — return ONLY a JSON array of finding
objects matching the schema below. No prose around it.

Window:   since=<SINCE>  until=<UNTIL>   (only consider activity in this window)
Scope:    <project | all | path>
Project dirs: <list>
Session files in window: <list of paths, or "use meta-cc">

How to read the history:
- PREFERRED: load meta-cc tools via ToolSearch (query "meta-cc"), then query
  with scope="project" (or loop working_dir over the project dirs for "all")
  and since/until set to the window. Use jq_filter and stats_only/stats_first
  to keep output small. See the query recipes you were given.
- FALLBACK (meta-cc unavailable/erroring): read the listed *.jsonl files
  directly with grep/jq. Do NOT Read whole files into context — filter first.

Rules:
- Every finding MUST cite evidence: at least one session_id plus a short quote
  or a turn/timestamp reference, and how often it recurred. No evidence → drop
  it. Do not speculate beyond what the logs show.
- Prefer a few high-signal findings over a long thin list. Deduplicate within
  your own output.
- Severity: important | significant | minor. Be honest; don't inflate.
- The user's environment rules live in their CLAUDE.md / CLAUDE.local.md — read
  them if relevant to your lens, but never act, only observe.
```

---

## Lens A · Workflow & repetition

Find recurring patterns and friction in how work actually flows.

- Sequences of steps that repeat across sessions (the same 4-tool dance, the
  same manual setup) — candidates to collapse or template.
- Friction: long back-and-forth to get to a clear ask, re-explaining the same
  context each session, repeatedly pasting the same paths/snippets.
- Places where the user or Claude took the long way around something that has a
  shorter path.
- Time/turn sinks: where did sessions spend a disproportionate number of turns
  relative to the outcome?

Useful signals: `get_work_patterns` (tool frequency, context switches),
`query_tools` frequency, `get_timeline`, repeated near-identical user messages
(`query_user_messages` with `group_by_session`).

## Lens B · Errors & dead-ends

Find mistakes, breakage, and wasted effort.

- Tool errors and what triggered them; commands re-run after failing without a
  changed approach (thrash).
- Dead-ends: an approach pursued for several turns then abandoned.
- Recurring failure modes (same error class across sessions).
- Cases where Claude claimed success but the evidence shows it wasn't verified.

Useful signals: `analyze_errors`, `query_tool_errors`, `query_system_errors`,
`query_tools(status="error")`, `analyze_bugs`, `quality_scan`.

## Lens C · Instruction adherence (both directions)

Compare Claude's behavior against the user's instructions — and judge the
instructions themselves.

- **Deviations**: where Claude did something CLAUDE.md / CLAUDE.local.md / a
  skill / an explicit user correction told it not to (or skipped something it
  was told to do). Cite the rule and the violating action.
- **User corrections**: places where the user had to repeat or re-correct the
  same guidance — a sign the instruction isn't landing.
- **Instruction quality** (reciprocal): rules that are missing, ambiguous,
  contradictory, stale, or so rigid they cause friction. Propose concrete
  wording or a new rule.

Read the actual CLAUDE.md / CLAUDE.local.md / relevant SKILL.md files. Signals:
`query_user_messages` for corrective phrasing ("no, I said…", "не надо",
"again", "stop"), `query_tools` for actions that contradict a known rule.

## Lens D · Skill & automation gaps

Find what should be automated or turned into reusable tooling.

- Multi-step sequences done by hand repeatedly that should be a **skill**,
  **hook**, **script**, or shell **alias**.
- Repeated permission prompts / approvals that a settings allowlist would remove.
- Existing skills the user isn't using when they'd help (under-triggering), or
  skills that misfire.
- One concrete proposed automation per finding (what it'd do, rough shape).

Signals: repeated tool sequences (`query_tools`), repeated Bash command
shapes, frequency of the same manual workflow across sessions.

## Lens E · Tech & approach quality

Judge the technology and engineering choices visible in the sessions.

- Suboptimal library / tool / command choices (a heavier or deprecated tool
  where a standard/better one exists; reinventing something already available).
- Anti-patterns in the code or commands actually written.
- Architecture / data-flow decisions that recur and could be done better.
- Better-fit alternatives — name the specific replacement and why.

Be concrete and current; tie each claim to something in the logs (a command, a
file edit, a snippet). This lens is about the user's technical approach, not
Claude's process (that's the other lenses).
