---
name: systems-review
description: "Periodic audit of codebase subsystems. Picks N stale systems from docs/SYSTEMS.md, runs topic-driven review (bugs, completeness, dry, architecture, consistency, efficiency, tests, docs-sync, security?), shows a per-system plan in plan mode, and applies fixes in isolated worktrees before stamping last_review. Invoke as /systems-review [count] [subsystem]."
disable-model-invocation: false
---

You are the main agent for the `/systems-review` skill. The user invoked you to audit codebase subsystems. Follow this flow exactly.

## Inputs

User input is in `$ARGUMENTS`. Parse in this order:

1. Detect flags (any position): `--yes`, `-y`, `--auto` → set `non_interactive = true`. Strip them from the token list.
2. The first remaining numeric token → `count`.
3. All other remaining tokens (joined) → `subsystem` filter.
4. Either `count` or `subsystem` may be absent. Default `non_interactive = false`.

Examples:
- `8` → count=8, subsystem=none, non_interactive=false
- `flutter` → count=default, subsystem="flutter", non_interactive=false
- `flutter 4` → count=4, subsystem="flutter", non_interactive=false
- `--yes 5 flutter` → count=5, subsystem="flutter", non_interactive=true
- `-y` → count=default, subsystem=none, non_interactive=true
- (empty) → count=default, subsystem=none, non_interactive=false

## Configuration
Load the merged config by running:

```bash
bash ${CLAUDE_SKILL_DIR}/bin/load-config.sh
```

This prints a single JSON object combining built-in plugin defaults with any user override at `<repo-root>/.claude/make-better.config.json`. All knobs (`registry_path`, `review_stale_after_days`, etc.) come from this object. Do not read any config file directly — always go through the loader.

Apply user `count` only if it is `<= max_systems_per_run`; otherwise clamp and inform the user.

### User-facing language
The config has a `user_language` field (default `"en"`). Render **every user-facing message** in this language: status lines, plan mode content, AskUserQuestion prompts and option labels, the final report, error messages. The instructions in this skill, JSON shapes exchanged with sub-agents, commit messages, branch names, and code stay in English regardless. Translate only what the user reads.

## Non-interactive mode (`--yes`)

When `non_interactive` is true (set via `--yes` / `-y` / `--auto`), every step below that would normally pause for user input must instead resolve automatically. The rules:

1. **Plan mode (Phase 2):** skip entirely. Do not enter plan mode, do not call `AskUserQuestion`, do not show the "approve / modify / cancel" UI. Treat the computed plan as approved-as-is and proceed straight to Phase 3 (implementation).
2. **Stale peer lockfiles (0.4):** auto-delete and log one line: `auto-removed stale lockfile <name> (started_at <ts>) due to --yes`. Do not prompt.
3. **Any other `AskUserQuestion`** (merge conflict ambiguity in 3.5, ambiguous failure in Phase 4, anywhere else):
   - If there is a documented safe default for that question, pick it and log: `auto-picked "<option>" because of --yes`.
   - If there is no safe default, **skip the affected unit of work** (the system, the section, whatever is at hand): mark its `status` in your in-memory plan as `skipped_for_human`, attach the question text and any relevant context as `blocker`, and continue with the rest. Do **not** stamp `last_review` for skipped systems.
4. **Hard errors are still hard.** Missing registry, dead lockfile that you can't safely remove, broken config — these still abort. `--yes` only suppresses *prompts that have an answer the agent can produce*.
5. **`status: needs_user_decision` systems are still skipped from the candidate pool**, regardless of `--yes`. Auto-mode does not retroactively decide what humans previously deferred.
6. **Final report (Phase 5):** add a `Skipped — human decision needed` section listing every system or sub-step that was deferred because there was no safe default. The user reviews this section after the unattended run.

If `non_interactive` is false (default), every prompt and plan mode behaves as documented in the rest of this skill.

## Phase 0 — Bootstrap

### 0.1 Verify registry exists
Read `<registry_path>` (default `docs/SYSTEMS.md`). If the file is missing or has no `### ` headings:

> Stop with: "No systems registry found at `<path>`. Run `/systems-discover` first to populate it."

Exit cleanly. Do not auto-invoke discovery.

### 0.2 Parse the registry
Walk the file line by line:
- `## <name>` — current section.
- `### <name>` — current system, attached to current section.
- `- key: value` under a system — set field.
- `- value` under a previously seen `- areas:` — append to that system's `areas` list.
- Other lines under a system — ignored.

Result: ordered list of systems with `{ section, name, last_review, status, blocker, areas, notes }`.

### 0.3 Build candidate pool

Apply filters in order:

1. **subsystem filter (semantic):** if user provided a filter, look at section names AND system names AND notes. Decide which systems plausibly match. Be generous: `flutter` matches any system in a "Flutter App" section AND any system whose name or notes mention flutter. Use judgement.
2. **drop `status: needs_user_decision`** — these need manual resolution.
3. **drop locked systems:** read every `<lockfile_dir>/.systems-review.*.lock`. Union their `systems` arrays. Drop those.
4. **drop systems touched by the working tree:** run `git status --porcelain` (and if needed `git diff --name-only HEAD`) to get the list of modified/staged/untracked files. For each remaining system, if **any** of its `areas:` paths overlaps with that file list (file lives under an area directory, or matches an area glob), drop the system. Goal: avoid merge conflicts between the in-progress user changes and the implementer's branch. A path overlap counts even for untracked files.
5. **drop fresh systems:** for each remaining system, if `last_review` is set AND newer than `(today - review_stale_after_days)`, drop. Keep systems with no `last_review`.

If the pool is empty, tell the user with a brief diagnostic: "No stale systems matching `<filter>` (X total in registry, Y filtered out by status, Z locked by other runs, D touched by working-tree changes, W still fresh). Try a broader filter, commit/stash your changes, or use a shorter staleness window."

### 0.4 Detect stale lockfiles
Liveness is determined by **age of `started_at`**, not pid. Claude Code agents have no stable OS pid they can record (every Bash call is a fresh subshell), so a pid field is unreliable here — ignore it for liveness decisions.

For each peer lockfile (anyone's, not just yours):
- If `started_at` is within the last `stale_lockfile_after_hours` (default 3h): treat as a **live peer run**. Do nothing — its systems are already excluded by 0.3.3, and you proceed silently in parallel. Do not prompt the user.
- If `started_at` is older than that threshold: treat as **stale** (likely a crashed or aborted run). Prompt the user once:

> "Found stale lockfile `<filename>` from `<started_at>` (older than <N>h). Remove? (y/n)"

Do not auto-delete. Do not delete other runs' lockfiles unless the user approves here.

### 0.5 Sample N systems
Sample `count` systems from the pool. Weight toward oldest `last_review` (and treat `null` as "infinitely old" — those go first). If pool < `count`, take all and inform the user.

### 0.6 Write own lockfile
Compute slug:
- `filter_slug` = lowercased filter, non-alphanum → `-`, or `all` if no filter.
- `timestamp` = `YYYYMMDD-HHMMSS` UTC.
- lockfile name: `<lockfile_dir>/.systems-review.<filter_slug>-<timestamp>.lock`

Content:
```json
{
  "started_at": "<ISO 8601 UTC>",
  "filter": "<original filter or empty>",
  "systems": ["<system_name>", "..."]
}
```

Do not write a `pid` field — Claude Code agents have no stable OS pid (every Bash call is a fresh subshell, so any value would be meaningless). Liveness is determined entirely by `started_at` age (see 0.4).

Remember the lockfile path — you must delete it on every exit path. Wrap the rest of the run in try/finally semantics: if anything below throws, abort, delete the lockfile, surface the error.

### 0.7 Tell the user
Print a one-line status:

> "Picked N systems for review: <comma-separated names>. Filter: <filter or 'none'>. Stale threshold: <days> days. Lockfile: <path>."

## Phase 1 — Review (parallel)

For each picked system, dispatch a review agent in parallel via the Agent tool. Cap concurrency at `max_parallel_review_agents`. If you have more systems than slots, run in waves.

For each review agent:
- `subagent_type`: `general-purpose`
- `model`: `<review_agent_model>` (default `opus`)
- prompt: contents of `.claude/skills/systems-review/prompts/review-agent.md` plus the system fields, the topic docs (read every `topics/*.md`), the topic lists, repo root, and today's date.

Collect all returns. For each:
- `verdict: "proceed"` → keep the system in the active set.
- `verdict: "empty_plan"` → keep, but its plan section is the empty-plan template.
- `verdict: "system_removed"` → keep, but its plan section is the removed template; finalization will drop it from the registry.
- `verdict: "needs_user_decision"` → keep, but the section shown to the user explains the blocker; on approve, the registry is updated with the blocker (no implement phase for this system).

If any review agent throws or never returns sensibly, treat as `needs_user_decision` with blocker "review agent failed; rerun".

## Phase 2 — Plan mode

Render the plan in the configured `user_language`. The plan is a **compact summary** — no file lists, no risks/tests sections. Just one bullet per change per system, brief but specific enough that the user knows what is being touched.

### 2.1 Render the plan

Group systems by their section (the H2 from `SYSTEMS.md`). Within a section, list each system with a compact bullet list:

```md
## <Section name>

### <System name>
- <one short sentence describing the fix/change/addition>
- <next bullet>
- ...

### <Another system in the same section>
- ...

## <Next section>
...
```

Bullets describe **what changes**, not where or how. Example:

```md
## Auth

### Google Auth (web → server)
- Unify 401 handling — single error mapper instead of two divergent paths
- Stop logging session token in the error path
- Add a unit test for the mapper

### Telegram Auth (bot → server)
- Replace silent retry on session refresh failure with explicit re-auth
- Update notes after recent middleware rename
```

Keep each bullet under ~120 characters. Skip items that are pure noise. Don't list every individual finding from every topic — fold related findings into one bullet when they describe the same change.

For systems with verdict `"empty_plan"`: render only the system heading with `_(no changes — review pass)_` and skip the bullet list.

For systems with verdict `"system_removed"`: render `_(system removed — no longer in code)_`.

For systems with verdict `"needs_user_decision"`: render `_(needs decision: <blocker>)_` — these get the blocker recorded but no implement run.

### 2.2 Overall summary (always at the end of the plan)

After all sections, render this block:

```md
---

**Overall:** Found <N> issues across <M> systems.
- <count> bug fixes (auto-applied)
- <count> DRY refactors
- <count> architecture cleanups
- <count> consistency fixes
- <count> efficiency improvements
- <count> test additions / fixes
- <count> docs sync updates
- <count> completeness gaps
- <count> security issues               (only if any — drop the line if zero)

**Needs your attention:**
- <System>: <plain-language description of an implicit decision, behavior change, or anything that could give an unexpected result>
- ...
```

Rules for the **Needs your attention** section — this is the most important part of the plan:

- **Bugs are auto-applied** without flagging. Do NOT list bug fixes here.
- **Logic / behavior changes MUST be flagged.** Ideally a review pass changes no observable behavior, only structure. If anything in the plan changes runtime behavior — even subtly (different error type, different default, different timing, different log shape that downstream parses, different ordering of effects) — surface it here in plain language. Describe what the user/system would observe before vs after.
- **Implicit decisions MUST be flagged.** If the implementer would have to choose between two reasonable approaches (LWW vs vector-clock, string vs enum, etc.) and your plan picked one — say which one and why. The user can override before approving.
- **Risky refactors** that touch shared code paths used by other systems: flag them.
- **API contract changes** (even internal): flag them, name the contract.

If there is **nothing** to flag (pure bugs + structure-only refactors), write: `_No behavior changes — bug fixes and structure-only refactors only._`

### 2.3 Approval prompt — use AskUserQuestion

After printing the plan, call the **AskUserQuestion** tool to capture the user's decision via arrow-key + Enter UI. Build the `questions` argument with **one** question. The first option is always "approve as-is"; then 2–3 dynamically chosen options based on what is in the plan; finally a "modify / cancel" path.

If AskUserQuestion is not loaded yet, use ToolSearch with `select:AskUserQuestion` to load it before calling.

Build options like this (one question, multiple options, single-choice):

| Always present | Present only when applicable |
|---|---|
| **Approve and execute** (always option 1) | **Drop behavior changes** — apply only bug fixes and structure-only refactors (when the plan has any "Needs your attention" item that is a behavior change) |
| **Modify the plan** (free-text follow-up) | **Defer `<System X>`** — skip this system, keep its `last_review` unchanged (when one system carries the bulk of risky changes) |
| **Cancel** | **Drop the cross-cutting refactor in `<area>`** — keep the rest (when the plan includes a refactor that crosses several systems) |
|   | **Apply only `<Section X>`** — skip other sections this run (when there are 4+ systems and the user might want to start narrow) |

Pick **2–3** of the conditional options that best match the plan's actual risks. Skip "Approve" of course is always there. After "Approve", come the conditional ones, then "Modify" and "Cancel" as the last two.

Each option's `label` and `description` go to the user, so write them in `user_language`. Question header: short, like "Approve plan?" / "Утвердить план?".

### 2.4 Handle the response

| User picks | What you do |
|---|---|
| Approve and execute | Proceed to Phase 3. |
| Drop behavior changes | For every system whose plan contains a behavior-change item flagged in "Needs your attention", remove that item from `detailed_plan`. Re-render the plan and re-prompt with AskUserQuestion. |
| Defer `<System X>` | Remove that system from the active set (no `last_review` update for it). Re-render and re-prompt. |
| Drop cross-cutting refactor / Apply only `<Section X>` | Apply the corresponding scope reduction. Re-render and re-prompt. |
| Modify the plan | Drop out of AskUserQuestion. Wait for the user's free-text instructions. Apply edits per the "Edit handling" rules below. After edits, re-render the plan and call AskUserQuestion again. |
| Cancel | Skip Phase 3 and Phase 4 code path; still run cleanup (lockfile, etc.). |

### Edit handling (free-text iteration after "Modify the plan")

When the user edits, classify:

- **Trivial edits** (drop a step, rename a path because the user knows it's better, mark a system as skip-and-don't-bump, reorder steps): silently update both `user_spec` (the rendered bullets) and `detailed_plan` (full instructions for the implementer) in your memory. Show a small diff. Re-call AskUserQuestion.
- **Non-trivial edits** (replace approach, add scope, "are you sure this is correct?"): investigate. You already hold `raw_findings` from each topic — start there. If you need fresh data on something narrow, dispatch ONE topic agent (the one most relevant) with a focused query. Then reply to the user with: consequences of their proposed change, alternatives if any look better, and end with "update the plan?". On confirmation, update the plan in your memory. Otherwise, leave it. Re-call AskUserQuestion.

If the user's edit pulls scope outside the system's `areas:`, warn them: "This change touches `<other path>`, which belongs to system `<other system>` (or no registered system). Apply anyway?"

## Phase 3 — Implement (parallel)

For every system with `verdict: "proceed"` (after edits) AND not skipped:

- Compute slug for the branch: `<branch_prefix>/<filter_slug>-<timestamp>/<system_slug>` where `system_slug` is the system name lowercased with non-alphanum → `-`.
- Dispatch an implement agent via the Agent tool:
  - `subagent_type`: `general-purpose`
  - `model`: `<implement_agent_model>` (default `opus`)
  - `isolation`: `worktree`
  - prompt: contents of `prompts/implement-agent.md` plus `system_name`, `detailed_plan`, `branch_name`, `areas`, `repo_root` (the worktree path).

Cap concurrency at `max_parallel_implement_agents`.

Collect each return:
- `verdict: "success"` with `branch` and `commit_sha` → mark for merge.
- `verdict: "needs_user_decision"` with `blocker` → mark for status update; do NOT merge its branch (clean it up).

Systems with `verdict: "empty_plan"` and `system_removed` skip Phase 3 entirely — no implementer needed.

## Phase 4 — Merge & finalize

### 4.1 Merge implementer branches sequentially
For each successful branch, in pick order:

```
git merge --no-ff <branch_name>
```

If clean, continue. If conflict:
- Read the conflicted file.
- Use the system's `detailed_plan` as ground truth for the system's intent.
- If both systems' intents are independent (different lines, different functions), combine them.
- If they touched the same lines, prefer the version consistent with both plans. If the resolution is still ambiguous, **ask the user** — do not guess on truly ambiguous content.
- After resolving: `git add <files> && git commit --no-edit` (the merge commit message is fine; or amend message to reference the system).

After each successful merge:
- Delete the branch (`git branch -d <branch_name>`).
- The Agent tool cleans up worktrees automatically once they're merged.

### 4.2 Run full lint and test
From repo root:

```
pnpm lint
pnpm test
```

If they pass: continue.
If they fail:
- If the failure is unambiguous and small (shared type changed in two places, missing import in a file shared between two merged systems), fix it directly. Commit: `fix(systems-review): integration fixup after merging N systems`.
- If the failure is ambiguous, ask the user. Do not roll back.
- Either way, `last_review` for systems that merged cleanly still updates.

### 4.3 Update SYSTEMS.md
Read the current registry. For each system in this run, apply the appropriate change in place:

| Outcome | Change |
|---|---|
| success (merged cleanly OR with auto-resolved conflict) | `last_review: <today>`. Clear `status` and `blocker` if they were set. |
| empty_plan, user approved | `last_review: <today>`. No code change. |
| system_removed, user approved | Delete the entire `### <system>` block (and its fields). Leave the `## section` heading even if it becomes empty. |
| needs_user_decision (from review or implement) | Set `status: needs_user_decision (since <today>)`. Set `blocker: "<one-line>"`. Do not change `last_review`. |
| user dropped this system in Phase 2 | No change. |
| areas_corrections present | Replace the `- areas:` block with the corrected list. |

Preserve order of sections and systems. Minimize the diff.

Commit:
```
chore(systems): update review dates (<N successful>, <M needs decision>, <K clean>, <L removed>)
```

### 4.4 Delete own lockfile
`rm <lockfile_path>`. Always. Even on failure of Phase 4.

### 4.5 Print final report

The final report is rendered in `user_language`. It has two parts:

**Part 1 — bucket counts** (one-line each):

```
✅ Successful: N
⚠ Needs user decision: M
✓ Clean (no changes): K
🗑 Removed: L
📝 Registry corrections: P
Full lint+test after merges: PASS / FAIL (<details>)
```

**Part 2 — per-system detail**, grouped by section. For every system that ran (success or needs-decision or clean), print one block. Skip the per-system block for "Removed" — they are already mentioned in the counts.

```
📁 <Section name>

### <System name> ✅
   What was done:
     - <bullet from user_bullets — only items actually applied>
     - ...
   Verify manually:
     - <what>
       <how>
     - <what>
       <how>
   Commits: <short-sha> [, <short-sha>]
   last_review: <today>

### <System name> ⚠ needs decision
   Blocker: "<one-line>"
   What is needed: <one-line — what the user must do to unblock>
   Branch (if implementer started): <branch_name>

### <System name> ✓ clean
   No changes — review pass. Tests are green, structure is fine, docs match.
   last_review: <today>
```

Rules:

- For successful systems: `What was done` is the actual `user_bullets` minus any items the user dropped during plan-mode iteration. `Verify manually` comes from the review agent's `manual_checks` field. If `manual_checks` is empty, render `Verify manually: none needed.`.
- For needs-decision systems: short — just the blocker, what the user must do, and (if any) a branch left behind. No manual checks here.
- For clean systems: just one line. No manual checks needed.
- Group by section using the H2 names from `SYSTEMS.md`. Sections only appear if they have at least one system to render.

**Closing line:**

```
Branches not pushed. Run `git push` when ready.
```

Example (rendered in `user_language: "en"`, fictional run):

```
✅ Successful: 2
⚠ Needs user decision: 1
✓ Clean (no changes): 1
🗑 Removed: 0
📝 Registry corrections: 1
Full lint+test after merges: PASS

📁 Auth

### Google Auth (web → server) ✅
   What was done:
     - Unified 401 handling — single error mapper instead of two paths
     - Stopped logging session token in error path
     - Added unit test for the mapper
   Verify manually:
     - 401 surfaces typed toast instead of raw error
       Open the app, clear cookies, watch the login screen — should show
       the typed ToastError with localized title.
     - Session token absent from server error logs
       Tail the server log after triggering an invalid login; grep for
       the token field — must be empty.
   Commits: 4a7d2f1
   last_review: 2026-04-29

### Telegram Auth (bot → server) ⚠ needs decision
   Blocker: "Two valid resolution strategies (LWW vs vector-clock); plan picked LWW but production behavior under concurrent edits is unverified."
   What is needed: pick LWW or vector-clock and update SYSTEMS.md status, then re-run.
   Branch: systems-review/all-20260429-1500/telegram-auth (left in place)

📁 Sync

### Snapshot Merger (server) ✅
   What was done:
     - Removed dead code path for legacy snapshots
     - Folded duplicate diff helpers into common/utils/diff.ts
   Verify manually:
     - New snapshots still write correctly
       Trigger a write in the dev environment and confirm the next
       snapshot appears with the expected delta count.
   Commits: 8f3e91c
   last_review: 2026-04-29

📁 Diagnostics

### Health Check (server) ✓ clean
   No changes — review pass. Tests are green, structure is fine, docs match.
   last_review: 2026-04-29

📝 Registry corrections:
   - Snapshot Merger → areas updated (server/src/services/sync/ moved)

Branches not pushed. Run `git push` when ready.
```

## Cleanup guarantees

On ANY exit (success, abort, exception):
1. Delete your own lockfile.
2. Do not delete other lockfiles unless the user explicitly approved their removal in Phase 0.4.
3. Leave any partially-created branches in place if Phase 3 was interrupted; tell the user which branches exist so they can review.

## Models
- You (main agent): your own model, whatever the harness gives you.
- Review agents: `<review_agent_model>` (opus by default).
- Implement agents: `<implement_agent_model>` (opus by default).
- Topic agents: `<topic_agent_model>` (sonnet by default).

## Files referenced
- `.claude/skills/systems-review/config.json` — all defaults.
- `.claude/skills/systems-review/prompts/review-agent.md` — review agent prompt.
- `.claude/skills/systems-review/prompts/implement-agent.md` — implement agent prompt.
- `.claude/skills/systems-review/topics/*.md` — one file per topic.
- `docs/SYSTEMS.md` — the registry (managed externally by `/systems-discover` and humans).
- `docs/.systems-review.*.lock` — runtime lockfiles, gitignored.
