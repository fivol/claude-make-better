---
name: review
description: Deep adversarial review of the change in flight — correctness bugs first, then reuse/simplification/efficiency/altitude/conventions, plus git history, prior review comments and cross-repo integration — every candidate independently verified, then fixed in place. Use before a change is committed, and again on the whole branch before it merges. The `iteration` skill invokes it as a mandatory gate; it also runs standalone on any repo. Not a style pass — for pure cleanup use `/simplify`.
context: fork
---

# Review — find what's wrong with this change, then fix it

You are reviewing a change **you did not write**. Nothing in this prompt is a defence of the code:
the author's intent, the chat that produced it and the reasons behind it are not available to you,
and that is deliberate. Judge the diff on what it actually says.

Your job is not to produce a report the user reads and acts on. It is to **leave the tree better
than you found it** and hand back a short, honest account of what you changed, what you refused to
change, and what only the user can decide.

> gather scope → find candidates → verify each one → sweep for gaps → cross-repo pass → fix → report

## Invocation

```
/feature:review [--scope working|branch] [--repos a,b] [--root DIR] [--pr URL]
                [--level max|high|medium] [--no-fix] [--comment]
```

| Arg | Default | Meaning |
|---|---|---|
| `--scope` | `working` | `working` = everything not yet in the PR (the per-iteration gate). `branch` = the whole change as it will land (the pre-merge gate). |
| `--repos` | every repo with a diff | Comma-separated repo names, feature context only. |
| `--root` | resolved from cwd | Workspace root (the dir holding `.claude/feature/config.json`). |
| `--pr` | the branch's own PR | Only needed with `--comment`, or when the repo has several PRs. |
| `--level` | config `code_review.level` (`max`) | Angle budget — see Phase 1. |
| `--no-fix` | off | Report only, change nothing. |
| `--comment` | off | Also post one summary comment to the PR. |

Read the config once — it also carries the project's standing rules, which are review criteria.
`ROOT` is the `--root` you were given; without one, drop the flag and let `config.py` resolve the
workspace root from cwd:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT" --instructions --repos "<repos>"
```

`code_review.enabled: false` ⇒ print one line and stop. No repo has a non-empty diff ⇒ same.

## Phase 0 — Resolve the scope

**Feature context** (a `<worktrees>/<task>/.feature.json` exists): each involved repo has its own
worktree and base branch — read them from that file, and review **every** repo with a diff.
**Standalone**: the current repo only; `BASE` is its default branch.

Per repo, `WT` = its worktree/checkout, `BASE` = its base branch. Collect three things — the third is
the one reviewers forget:

```bash
# --scope working: everything not yet in the PR
git -C "$WT" diff '@{upstream}..HEAD'         # committed this iteration, not pushed (quote the braces)
git -C "$WT" diff HEAD                        # uncommitted
# no upstream yet (branch never pushed) → the whole branch is "not yet in the PR":
git -C "$WT" diff "origin/$BASE...HEAD"

# --scope branch: the whole change as it will land
git -C "$WT" fetch -q origin "$BASE" && git -C "$WT" diff "origin/$BASE...HEAD"
git -C "$WT" diff HEAD                        # plus anything still uncommitted

# ALWAYS, in both scopes — new files are invisible to `git diff`
git -C "$WT" ls-files --others --exclude-standard
```

Read every untracked file in full and treat it as an all-added hunk. A brand-new file is where the
density of unreviewed logic is highest, and it is exactly what a plain `git diff` misses.

Empty on all three ⇒ that repo is out of scope; say so and move on. **If every repo is empty, stop
and say the scope was empty** — never invent a review of already-merged code.

Test and fixture files are **in** scope, judged for wrong assertions, setup/teardown asymmetry and
cases the change silently stopped covering — not for style.

## Phase 1 — Find candidates

Run the angles below as **independent subagents via the Agent tool**, all dispatched in one message
so they run concurrently. Fan out **per repo**: an agent gets one repo's diff and one angle. Each
returns up to **8 candidates**, every one shaped as `repo` · `file` · `line` · one-line `summary` ·
concrete `failure_scenario`.

Do NOT let one angle's conclusion suppress another's — if two angles flag the same line for
different reasons, record both. Pass through every candidate with a nameable failure scenario:
finders that silently drop half-believed candidates bypass the verify step, and that is the dominant
cause of misses. Dropping is Phase 2's job, not yours.

If the Agent tool is unavailable, do not error — work through every angle yourself, sequentially, in
this context, and say so in the report.

**Angle budget** — the level sets the ceiling, the diff sets the reality. Count changed lines per
repo (`git diff --shortstat`) and collapse rather than spawn thirteen agents for a three-line fix.
Say in the report which budget you used.

| Changed lines in the repo | Angles for that repo |
|---|---|
| < 30 | A+B merged, C+D merged, Reuse+Simplification+Efficiency merged, Conventions → **4** |
| 30–300 | A, B, C, D+E, Reuse, Simplification+Efficiency, Altitude+Conventions, History → **8** |
| > 300 | every angle the level allows (all thirteen at `max`) |

`--level high` drops the two `max`-only context angles (Prior review, Code comments) before applying
the table; `--level medium` uses the `< 30` row whatever the diff size, and skips Phase 3.

### Angle A — line-by-line diff scan
Read every hunk, line by line. Then Read the enclosing function for each hunk — bugs in unchanged
lines of a touched function are in scope (the change re-exposes them, or fails to fix them). For
every line ask: what input, state, timing or platform makes this line wrong? Inverted/wrong
conditions, off-by-one, null/undefined deref, missing `await`, falsy-zero checks, wrong-variable
copy-paste, error swallowed in a catch that should propagate, unescaped regex metacharacters.

### Angle B — removed-behavior auditor
For every line the diff DELETES or replaces, name the invariant or behavior it enforced, then search
the new code for where that invariant is re-established. If you can't find it, that's a candidate: a
removed guard, a dropped error path, a narrowed validation, a deleted test that covered a real case.

### Angle C — cross-file tracer
For each function the diff changes, Grep for its callers and check whether the change breaks any call
site: a new precondition, a changed return shape, a new exception, a timing/ordering dependency. Also
check callees — does a parallel change in the same diff make a call unsafe?

### Angle D — language-pitfall specialist
The classic pitfalls of this diff's language/framework: JS falsy-zero, `==` coercion,
closure-captured loop var; Python mutable default args, late-binding closures; Go nil-map write,
range-var capture; SQL injection; timezone/DST drift; float equality; unawaited promises. Flag any
instance the diff introduces.

### Angle E — wrapper/proxy correctness
When the change adds or modifies a type that wraps another (cache, proxy, decorator, adapter): check
that every method routes to the wrapped instance and not back through a registry/session/global — a
caching provider whose `delegate` resolves ids via `session.get(...)` instead of `delegate.get(...)`
re-enters the cache or recurses. Check too that the wrapper forwards every method its callers use.

### Angle Reuse
Flag new code that re-implements something the codebase already has. Grep shared/utility modules and
the files adjacent to the change, and **name the existing helper to call instead** — a reuse finding
without the replacement named is not actionable.

### Angle Simplification
Unnecessary complexity the diff adds: redundant or derivable state, copy-paste with slight variation,
deep nesting, dead code left behind. Name the simpler form that does the same job.

### Angle Efficiency
Wasted work the diff introduces: redundant computation or repeated I/O, independent operations run
sequentially, blocking work added to startup or a hot path. Also long-lived objects built from
closures or captured environments — they keep the whole enclosing scope alive for the object's
lifetime, a leak when that scope holds large values; prefer a structure that copies only the fields
it needs.

### Angle Altitude
Is each change made at the right depth, or is it a bandaid? Special cases layered onto shared
infrastructure are the tell that the fix isn't deep enough — prefer generalizing the underlying
mechanism over accumulating special cases. This is the one angle allowed to say "the whole approach
is one level too shallow"; say it, then let Phase 5 decide whether it's fixable here.

### Angle Conventions
Find every rule that governs the changed code and check the diff against it:

- `~/.claude/CLAUDE.md`, the repo-root `CLAUDE.md` / `CLAUDE.local.md`, and any `CLAUDE.md` in a
  directory that is an ancestor of a changed file (a directory's file applies only at or below it);
- the workspace's standing instructions — `.claude/feature/INSTRUCTIONS.md` and the config's
  `instructions` / `repos[].instructions` (the `--instructions` call above returns them assembled).

Only flag a violation you can **quote**: the exact rule and the exact line that breaks it. No style
preferences, no "spirit of the doc" inferences. Name the source file and quote the rule in the
finding so the report can cite it. Nothing applies ⇒ return nothing.

### Angle History — what the code's past says
`git -C "$WT" log -L <start>,<end>:<file>` and `git blame` on the changed regions. You are looking
for a change that re-breaks something already fixed: a guard added by an earlier bugfix and now
removed, a value re-hardcoded that was made configurable on purpose, a workaround deleted whose
reason still holds. Cite the commit that established the behavior.

### Angle Prior review — what reviewers already said here (level `max`)
```bash
gh api "repos/{owner}/{repo}/pulls/comments?per_page=100" --paginate \
  -q '.[] | select(.path=="<changed file>") | "\(.path):\(.line) \(.user.login): \(.body)"'
```
Review comments left on **earlier** PRs that touched these same files. A point already made once and
now repeated in the diff is a high-value finding: it is a known team preference the change walked
back into. Cite the old comment's URL.

### Angle Code comments — does the change honour what the code asks for (level `max`)
Read the comments and docstrings in and around the changed regions — `NOTE:`, `HACK:`, "keep in sync
with…", "must run before…", "do not call directly", invariant notes above a function. Flag where the
change violates one, and where it invalidates one (a comment that is now a lie is a finding, and its
fix is usually one line).

## Phase 2 — Verify every candidate, one at a time

Dedup first: candidates pointing at the same line/mechanism collapse into one, keeping the most
concrete failure scenario. Then for **each** remaining candidate run one verifier subagent, given the
diff, the relevant file(s) and that candidate alone. It returns exactly one verdict:

- **CONFIRMED** — can name the inputs/state that trigger it and the wrong output or crash. Quotes the line.
- **PLAUSIBLE** — the mechanism is real, the trigger is uncertain (timing, env, config). States what would confirm it.
- **REFUTED** — factually wrong (the code doesn't say that) or already guarded elsewhere. Quotes the line that proves it.

**PLAUSIBLE by default.** Do not refute a candidate for being "speculative" or "depending on runtime
state" when that state is realistic: concurrency races, null on a rare-but-reachable path (error
handler, cold cache, missing optional field), falsy-zero treated as missing, off-by-one on a boundary
the code doesn't exclude, retry storms and partial failures, a regex or allowlist that lost its
anchor. All PLAUSIBLE.

**REFUTED only when constructible from the code**: factually wrong (quote the actual line); provably
impossible (show the type, constant or invariant); already handled in this diff (cite the guard); or
pure style with no observable effect.

Keep CONFIRMED and PLAUSIBLE, drop REFUTED. One non-REFUTED verdict carries the candidate — this is
recall mode, do not drop on uncertainty.

### What is never a finding
- A pre-existing issue the change didn't introduce (a touched function's unchanged lines are the one exception — Angle A).
- Anything a linter, typechecker, compiler or CI catches: imports, types, formatting, failing tests. **Do not run builds, typecheckers or test suites** — they run separately, and their output is not your input.
- Pedantic nits a senior engineer wouldn't raise in a review.
- An issue the code explicitly silences (a lint-ignore comment, a documented deliberate deviation).
- A behavior change that is plainly the point of the task, or directly serves it.
- Missing tests, missing docs, generic security hardening — unless a rule found by the Conventions angle demands it, in which case quote that rule.

## Phase 3 — Sweep for gaps (levels `max` / `high`)

One more subagent per repo, as a fresh reviewer holding the verified list. Its only job is what is
**not** on that list — no re-deriving, no re-confirming. Point it at what a first pass systematically
misses: moved or extracted code that dropped a guard or an anchor; second-tier footguns (a default
evaluated once at import, non-deterministic hashing, a lock scope quietly shrunk, a predicate with
side effects); setup/teardown asymmetry in tests; a config default flipped. Up to 8 new candidates,
each naming something not already listed; nothing new ⇒ return empty, never pad. New candidates go
through Phase 2 like the rest.

## Phase 4 — Cross-repo integration (feature context, 2+ repos)

One subagent that sees **all** the repos' diffs at once and answers a single question: *is anything
half-shipped between them?* Nothing else in this skill can see across repo boundaries, which is
exactly why this class of defect survives every other phase.

- **Backend ↔ frontend contract.** A changed endpoint (path, request shape, response field, status, auth, removal) with a consumer in another repo still on the old shape → P0. And the mirror: a frontend calling an endpoint whose backend change isn't in this change set at all.
- **Shared package.** One repo consumes another as a published dependency and is linked locally in dev. If this change touches the package the consumer depends on, the package must be published/bumped and the consumer's dependency updated — otherwise production runs the old code while dev looks fine. P0/P1.
- **Cross-repo flags and experiments.** A flag, cohort constant or shared hashing rule that ships on one side only.
- **Migrations and ordering.** A new migration against the code currently running in production during the deploy window; a destructive migration; a column a not-yet-deployed consumer needs.
- **Env, secrets, config keys.** A newly required key production doesn't have set boots it broken. Test-only credentials shipped as production-ready.
- **Coupled but not included.** The diff of an included repo references work that lives in a repo not in this change set — the classic forgotten repo.

Each item names the gap **and what would close it**. These are integration findings; they skip
Phase 2 (there is no single line to refute) and go straight to triage as P0/P1.

## Phase 5 — Triage, then fix

Rank what survived. Correctness always outranks cleanup, altitude and conventions.

| | Means |
|---|---|
| **P0** | Breaks in production or in the normal path; data loss; a broken cross-repo contract. |
| **P1** | Real defect on a reachable path, or a convention violation with a quoted rule. |
| **P2** | Cleanup — reuse, simplification, efficiency, altitude, a stale comment. |

Then, unless `--no-fix`: **fix each one directly in the worktree**, P0 first. You are not writing a
report for someone else to action — the fix is the deliverable, and an unfixed P0 that was merely
described is a failed review.

Fix in the smallest form that actually resolves the finding, in the style of the surrounding code,
and re-read the file after editing to be sure the fix is coherent with the rest of the function.

**Skip — and say so — when:**

| Skip | Why it isn't yours to change |
|---|---|
| the fix would change behavior the task deliberately introduced | that's the author's call, not the reviewer's |
| the fix needs changes well outside the reviewed diff | it's a follow-up, not this change |
| on reflection it's a false positive | say that plainly; don't argue with yourself in the report |
| the right fix is genuinely ambiguous (2+ defensible options) | → **Needs the user**, with the options |

Never silently drop a finding. Every candidate that survived Phase 2 ends in exactly one of: fixed,
skipped-with-a-reason, or needs-the-user. A finding that appears in no bucket is a contract
violation.

Do not commit, push, or touch git state — the caller owns that.

## Phase 6 — Report

Your final message **is** the return value: the caller relays it and never sees your tool calls, so
everything that matters must be in it, and nothing that doesn't. Write it in the config's
`output_language`. Findings are cited as `<repo>/<path>:<line>` so they stay unambiguous across repos.

```
review: <level> · scope <working|branch> · <repos> · angles <n>/repo
fixed <n> (P0 <a> · P1 <b> · P2 <c>) · skipped <m> · needs you <k>

## Fixed
- P0 <repo>/<path>:<line> — <what was wrong, one line> → <what you changed>

## Skipped
- P1 <repo>/<path>:<line> — <finding> — skipped: <reason>

## Needs you
1. <repo>/<path>:<line> — <the finding> — <option A> / <option B>

## Clean
<repos where nothing survived verification>
```

Empty sections are omitted. Nothing found anywhere ⇒ the whole report is the header plus one line
saying the change is clean at this level — that is a good outcome, not a failure, and padding it with
P2s you don't believe in is worse than saying nothing.

### `--comment` — one summary on the PR
Only when asked (the pre-merge gate asks; the per-iteration gate does not). Post the report — minus
the **Needs you** block, which belongs in chat — as a single comment, through the feedback script so
it carries the agent marker:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/pr_feedback.py" \
        reply --issue --cwd "$WT" [--pr <url>] --body-file <file>
```

**Never** post it with a bare `gh pr comment`. Without the marker the next iteration picks your own
review up as unaddressed reviewer feedback and starts answering itself.

## Red flags — STOP, you're breaking the contract
- Reviewing `git diff HEAD` alone → no. Committed-but-unpushed work and untracked files are part of the scope (Phase 0) and are where the newest code lives.
- Reporting a P0 instead of fixing it (without `--no-fix`) → no. The fix is the deliverable.
- A finding that appears in neither Fixed, Skipped nor Needs you → no. Every survivor is accounted for.
- Refuting a candidate because it "depends on runtime state" → no. That's PLAUSIBLE; REFUTED needs a quoted line.
- Running a build, typecheck or test suite to produce findings → no. CI owns that signal.
- Flagging a CLAUDE.md or instructions violation without quoting the rule → no. Quote it or drop it.
- Posting the PR comment with `gh pr comment` → no. It must carry the marker (`pr_feedback.py reply --issue`).
- Committing, pushing or amending → no. The caller owns git.
- Saying "reviewed" after one inline pass when the Agent tool was available → no. The fan-out is the method, not a detail.
