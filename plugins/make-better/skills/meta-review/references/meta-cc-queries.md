# meta-cc query recipes

meta-cc analyzes Claude Code session history. Tools are **deferred** — load them
first: `ToolSearch` with query `meta-cc` (or `select:<exact_name>`). They're
named `mcp__plugin_meta-cc_meta-cc__<tool>`.

## Common params (most tools share these)

- `scope`: `"project"` (default — current project, all its sessions) or
  `"session"` (current session only). There is **no "all projects"** scope —
  for `--scope all`, loop `working_dir` over each project's real cwd, or use the
  raw-JSONL fallback.
- `working_dir`: override the cwd used to locate sessions (point at another
  project to review it).
- `since` / `until`: RFC3339 (`"2026-06-02T00:00:00Z"`) — set to the window.
  (Confirmed available on `query_user_messages`; for tools without explicit
  since/until, post-filter on the `timestamp` field via `jq_filter`.)
- `jq_filter`: raw jq, no surrounding quotes (e.g. `.[] | select(.status=="error")`).
- `stats_only` / `stats_first`: aggregate counts instead of (or before) records —
  use these to keep output small.

## By lens

**A · Workflow & repetition**
- `get_work_patterns(scope="project")` — tool frequency, hourly activity, context switches.
- `query_tools(scope="project", stats_only=true)` — tool usage distribution.
- `query_user_messages(pattern=".", scope="project", since=…, until=…, group_by_session=true, content_summary=true)` — message volume / repeated asks per session.
- `get_timeline(scope="project")` — session arc.

**B · Errors & dead-ends**
- `analyze_errors(scope="project")` — errors grouped by tool + type.
- `query_tool_errors(scope="project")` / `query_tools(status="error", scope="project")`.
- `query_system_errors(scope="project")` — harness/system-level errors.
- `analyze_bugs`, `quality_scan` — higher-level problem detection.

**C · Instruction adherence**
- Read the rule sources directly: `CLAUDE.md`, `CLAUDE.local.md`, relevant `SKILL.md`.
- `query_user_messages(pattern="(?i)\\b(no,? i said|не надо|again|stop|don'?t|не так|я же просил)\\b", scope="project", since=…, exclude_system_messages=true, context_turns=1)` — corrective moments.
- `query_tools` to spot actions contradicting a known rule (e.g. a prod write, a commit when not asked).

**D · Skill & automation gaps**
- `query_tools(scope="project")` + `jq_filter` to find repeated Bash command shapes / tool sequences.
- `get_work_patterns` — recurring context switches that hint at a missing workflow.
- Cross-check against installed skills (the available-skills list) to spot under-used or missing ones.

**E · Tech & approach quality**
- `query_tools(tool="Bash", scope="project")` + `query_tools(tool="Edit")` / `Write` — what commands and code were actually written.
- `jq_filter` on `.input` to inspect command lines / file contents for tool & pattern choices.

## Raw-JSONL fallback (meta-cc down)

The `plan` output lists every session file in the window. Filter, don't Read whole files:

```bash
# user messages in window (records have a `timestamp` and a `message` payload)
for f in <session files>; do
  jq -c 'select(.type=="user")' "$f"
done

# tool errors
jq -c 'select(.type=="assistant") | .. | objects | select(.is_error==true)' <file>

# count tool uses by name
jq -r 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") | .name' <files> | sort | uniq -c | sort -rn
```

Record shapes vary across Claude Code versions — inspect a couple of lines
(`head -5 <file> | jq .`) before committing to a jq path. Always scope to the
window by the record `timestamp`.
