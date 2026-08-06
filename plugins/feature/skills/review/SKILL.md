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

> gather scope → find candidates → verify in batches → sweep for gaps → cross-repo pass → check the
> tree is untouched → fix → report

## Invocation

```
/feature:review [--scope working|branch] [--repos a,b] [--root DIR] [--pr URL]
                [--level max|high|medium] [--no-fix] [--comment|--no-comment]
```

| Arg | Default | Meaning |
|---|---|---|
| `--scope` | `working` | `working` = everything not yet in the PR (the per-iteration gate). `branch` = the whole change as it will land (the pre-merge gate). |
| `--repos` | every repo with a diff | Comma-separated repo names, feature context only. |
| `--root` | resolved from cwd | Workspace root (the dir holding `.claude/feature/config.json`). |
| `--pr` | the branch's own PR | Only needed when the summary comment is posted, or when the repo has several PRs. |
| `--level` | config `code_review.level` (`max`) | Angle budget — see Phase 1. |
| `--no-fix` | config `code_review.fix` (`true` ⇒ fix) | Report only, change nothing. |
| `--comment` / `--no-comment` | `--scope branch` → config `code_review.final_comment` (`true`) · `--scope working` → off | Also post one summary comment to the PR. |

**Flags are overrides, never prerequisites.** Every default above comes from the config, so a caller
that passes nothing — or that describes the scope in prose — still gets the configured behavior. A
behavior that only happens when the caller remembers a flag is a behavior that doesn't happen.

Read the config once — it also carries the project's standing rules, which are review criteria.
`ROOT` is the `--root` you were given; without one, drop the flag and let `config.py` resolve the
workspace root from cwd:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT" --instructions --repos "<repos>"
```

`code_review.enabled: false` ⇒ print one line and stop. No repo has a non-empty diff ⇒ same.

## The fan-out — read-only agents, on two model tiers

Every agent this skill spawns in Phases 1–4 is **read-only**. Dispatch each one as:

```
Agent(subagent_type: "feature:review-finder", model: "<tier>", prompt: "<the brief>")
```

`feature:review-finder` ships with this plugin and has **no `Edit` and no `Write`** — a structural
guarantee, not a request in a prompt. If that subagent type doesn't resolve, retry `review-finder`;
if that fails too, fall back to `general-purpose`, put the read-only rule in the prompt **in full**,
and say in the report that the finders ran unsandboxed.

Why it is structural: a finder that "helpfully" fixes what it found writes code no one reviewed into
a diff the caller is about to commit — and it has already shipped regressions here. Finding is theirs;
fixing is Phase 5's, and Phase 5 is yours.

**Model tiers — pass `model` on every dispatch, never let it default.**

| Tier | `model` | Runs |
|---|---|---|
| **deep** | config `code_review.deep_agent_model` (`opus`) | Angles A, B, C, D, E, Altitude · the cross-repo pass (Phase 4) · verification of correctness candidates and of every P0 suspect |
| **light** | config `code_review.light_agent_model` (`sonnet`) | Angles Reuse, Simplification, Efficiency, Conventions, History, Prior review, Code comments · the sweep (Phase 3) · verification of cleanup candidates |

The split is by **what the agent must actually do**, not by how much the finding matters. Deciding
whether a condition inverts on an empty list is reasoning; quoting the rule out of a `CLAUDE.md`,
reading `git log -L` output, filtering `gh api` results or naming the helper that already exists is
retrieval. Running retrieval on the deep tier roughly doubles the cost of the run and finds the same
bugs.

If the Agent tool is unavailable, do not error — work through every angle yourself, sequentially, in
this context, and say so in the report.

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

Last thing before you fan out — snapshot each repo's working state so Phase 4.5 can prove nothing
wrote to it. Both files go inside that repo's git dir: per-worktree, and never listed by `git status`.
Two snapshots, because one isn't enough — the status catches files created or newly modified, the
patch catches an edit to a file that was already dirty before the review started.

```bash
GD="$(git -C "$WT" rev-parse --absolute-git-dir)"
git -C "$WT" status --porcelain > "$GD/feature-review.pre"
git -C "$WT" diff HEAD          > "$GD/feature-review.patch"
```

If those writes are refused (a sandbox that pins you to the worktree), run the two read commands
instead and keep their output to compare against in Phase 4.5.

## Phase 1 — Find candidates

Run the angles below as **read-only subagents** (see the fan-out contract above), all dispatched in
one message so they run concurrently. Each returns up to **8 candidates per repo it covers**, every
one shaped as:

`repo` · `file` · `line` · one-line `summary` · concrete `failure_scenario` ·
`class` (**correctness** | **cleanup**) · `p0?` (yes when the scenario is production breakage, data
loss or a broken contract)

`class` and `p0?` are not decoration — Phase 2 routes on them.

Do NOT let one angle's conclusion suppress another's — if two angles flag the same line for
different reasons, record both. Pass through every candidate with a nameable failure scenario:
finders that silently drop half-believed candidates bypass the verify step, and that is the dominant
cause of misses. Dropping is Phase 2's job, not yours.

### Angle budget — one budget for the whole run

Count changed lines **across all repos in scope** (`git diff --shortstat` per repo, plus the lines of
untracked files) and pick one row. That number is the angle count for the **run**. The number of
repos never multiplies it.

| Changed lines, all repos | Angles for the run |
|---|---|
| < 30 | A+B merged, C+D+E merged, Reuse+Simplification+Efficiency merged, Conventions → **4** |
| 30–300 | A, B, C, D+E, Reuse, Simplification+Efficiency, Altitude+Conventions, History → **8** |
| > 300 | every angle the level allows — **13** at `max` |

**One agent per angle, covering every repo in scope.** Hand it all the repos' diffs at once; it
returns candidates tagged by repo. The single exception: when **two or more repos each have > 300
changed lines**, the three per-hunk angles (**A**, **B**, **C**) get one agent per repo — those are
the angles that must read every line, and attention does not divide. Apply the split to the largest
repos first and stop when you hit the cap.

**Hard cap: 16 finder agents per run.** Whatever the split suggests, you never dispatch more; drop
back toward one agent per angle until you fit. Say in the report which row you used and how many
agents ran.

`--level high` drops the two `max`-only context angles (Prior review, Code comments) before applying
the table; `--level medium` uses the `< 30` row whatever the diff size, and skips Phase 3.

### Angle A — line-by-line diff scan · deep
Read every hunk, line by line. Then Read the enclosing function for each hunk — bugs in unchanged
lines of a touched function are in scope (the change re-exposes them, or fails to fix them). For
every line ask: what input, state, timing or platform makes this line wrong? Inverted/wrong
conditions, off-by-one, null/undefined deref, missing `await`, falsy-zero checks, wrong-variable
copy-paste, error swallowed in a catch that should propagate, unescaped regex metacharacters.

### Angle B — removed-behavior auditor · deep
For every line the diff DELETES or replaces, name the invariant or behavior it enforced, then search
the new code for where that invariant is re-established. If you can't find it, that's a candidate: a
removed guard, a dropped error path, a narrowed validation, a deleted test that covered a real case.

### Angle C — cross-file tracer · deep
For each function the diff changes, Grep for its callers and check whether the change breaks any call
site: a new precondition, a changed return shape, a new exception, a timing/ordering dependency. Also
check callees — does a parallel change in the same diff make a call unsafe?

### Angle D — language-pitfall specialist · deep
The classic pitfalls of this diff's language/framework: JS falsy-zero, `==` coercion,
closure-captured loop var; Python mutable default args, late-binding closures; Go nil-map write,
range-var capture; SQL injection; timezone/DST drift; float equality; unawaited promises. Flag any
instance the diff introduces.

### Angle E — wrapper/proxy correctness · deep
When the change adds or modifies a type that wraps another (cache, proxy, decorator, adapter): check
that every method routes to the wrapped instance and not back through a registry/session/global — a
caching provider whose `delegate` resolves ids via `session.get(...)` instead of `delegate.get(...)`
re-enters the cache or recurses. Check too that the wrapper forwards every method its callers use.

### Angle Reuse · light
Flag new code that re-implements something the codebase already has. Grep shared/utility modules and
the files adjacent to the change, and **name the existing helper to call instead** — a reuse finding
without the replacement named is not actionable.

### Angle Simplification · light
Unnecessary complexity the diff adds: redundant or derivable state, copy-paste with slight variation,
deep nesting, dead code left behind. Name the simpler form that does the same job.

### Angle Efficiency · light
Wasted work the diff introduces: redundant computation or repeated I/O, independent operations run
sequentially, blocking work added to startup or a hot path. Also long-lived objects built from
closures or captured environments — they keep the whole enclosing scope alive for the object's
lifetime, a leak when that scope holds large values; prefer a structure that copies only the fields
it needs.

### Angle Altitude · deep
Is each change made at the right depth, or is it a bandaid? Special cases layered onto shared
infrastructure are the tell that the fix isn't deep enough — prefer generalizing the underlying
mechanism over accumulating special cases. This is the one angle allowed to say "the whole approach
is one level too shallow"; say it, then let Phase 5 decide whether it's fixable here.

### Angle Conventions · light
Find every rule that governs the changed code and check the diff against it:

- `~/.claude/CLAUDE.md`, the repo-root `CLAUDE.md` / `CLAUDE.local.md`, and any `CLAUDE.md` in a
  directory that is an ancestor of a changed file (a directory's file applies only at or below it);
- the workspace's standing instructions — `.claude/feature/INSTRUCTIONS.md` and the config's
  `instructions` / `repos[].instructions` (the `--instructions` call above returns them assembled).

Only flag a violation you can **quote**: the exact rule and the exact line that breaks it. No style
preferences, no "spirit of the doc" inferences. Name the source file and quote the rule in the
finding so the report can cite it. Nothing applies ⇒ return nothing.

### Angle History — what the code's past says · light
`git -C "$WT" log -L <start>,<end>:<file>` and `git blame` on the changed regions. You are looking
for a change that re-breaks something already fixed: a guard added by an earlier bugfix and now
removed, a value re-hardcoded that was made configurable on purpose, a workaround deleted whose
reason still holds. Cite the commit that established the behavior.

### Angle Prior review — what reviewers already said here (level `max`) · light
```bash
gh api "repos/{owner}/{repo}/pulls/comments?per_page=100" --paginate \
  -q '.[] | select(.path=="<changed file>") | "\(.path):\(.line) \(.user.login): \(.body)"'
```
Review comments left on **earlier** PRs that touched these same files. A point already made once and
now repeated in the diff is a high-value finding: it is a known team preference the change walked
back into. Cite the old comment's URL.

### Angle Code comments — does the change honour what the code asks for (level `max`) · light
Read the comments and docstrings in and around the changed regions — `NOTE:`, `HACK:`, "keep in sync
with…", "must run before…", "do not call directly", invariant notes above a function. Flag where the
change violates one, and where it invalidates one (a comment that is now a lie is a finding, and its
fix is usually one line).

## Phase 2 — Verify, in batches

Dedup first: candidates pointing at the same line/mechanism collapse into one, keeping the most
concrete failure scenario.

Then **batch — one verifier agent per batch, not per candidate.** A verifier per candidate does not
survive contact with a real diff: 40 candidates means 40 agents, so the phase gets quietly skipped
and fixes land on unverified findings. Batching is what makes this phase actually run.

| Batch | Size | Tier |
|---|---|---|
| **P0 suspects** (`p0?: yes`) | 1 — alone, always | deep |
| correctness candidates | group by file, **≤ 4** per batch | deep |
| cleanup candidates | group by file, **≤ 4** per batch | light |

Never mix classes in a batch. **Cap: 12 verifier agents** — over the cap, raise the non-P0 batch size
to 8; P0 suspects stay solo whatever happens. Dispatch every batch in one message.

Each verifier gets the diff, the relevant file(s) and its batch **numbered**, and returns **one
verdict per number, in order, and nothing else**. Fewer verdicts than candidates is a failed run:
re-dispatch the missing ones — never read a missing verdict as REFUTED.

Batching does not lower the bar. Each candidate is judged on its own evidence: a verifier must not
refute one because a neighbour in its batch was refuted, nor confirm one because a neighbour was
confirmed.

The verdicts:

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

## Phase 3 — Sweep for gaps (levels `max` / `high`) — and it always runs

One **light-tier** agent for the run, as a fresh reviewer holding the verified list. (One per repo
only when Phase 1's per-hunk split applied, i.e. 2+ repos over 300 changed lines each.) Its only job
is what is **not** on that list — no re-deriving, no re-confirming. Point it at what a first pass
systematically misses: moved or extracted code that dropped a guard or an anchor; second-tier
footguns (a default evaluated once at import, non-deterministic hashing, a lock scope quietly shrunk,
a predicate with side effects); setup/teardown asymmetry in tests; a config default flipped. Up to 8
new candidates, each naming something not already listed; nothing new ⇒ return empty, never pad. New
candidates go through Phase 2 like the rest.

This phase is one cheap agent. Skipping it because the run already feels big is a silent downgrade of
the level the caller asked for — if you truly cannot run it, say so in the report header.

## Phase 4 — Cross-repo integration (feature context, 2+ repos) · deep

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

## Phase 4.5 — The tree must still be untouched

Phases 1–4 are read-only by construction, so nothing in them can have changed a file. Prove it, per
repo, before you start fixing:

```bash
GD="$(git -C "$WT" rev-parse --absolute-git-dir)"
diff "$GD/feature-review.pre"   <(git -C "$WT" status --porcelain)   # must be empty
diff "$GD/feature-review.patch" <(git -C "$WT" diff HEAD)            # must be empty
```

A difference means a read-only agent wrote to the tree anyway — it happens when the
`feature:review-finder` type didn't resolve and you fell back to `general-purpose`. Those edits are
**not** review fixes: nothing verified them, and the caller is about to commit them under someone
else's name. The second `diff` shows you exactly which hunks appeared. Undo them — `feature-review.patch`
is the pre-review truth, so `git -C "$WT" checkout -- <path>` and re-apply the saved patch for that
path; a file the agent created is simply deleted. Then record it in the report as
`finders wrote to <n> file(s) — reverted`. Never carry an unexplained edit into Phase 5.

## Phase 5 — Triage, then fix

Rank what survived. Correctness always outranks cleanup, altitude and conventions.

| | Means |
|---|---|
| **P0** | Breaks in production or in the normal path; data loss; a broken cross-repo contract. |
| **P1** | Real defect on a reachable path, or a convention violation with a quoted rule. |
| **P2** | Cleanup — reuse, simplification, efficiency, altitude, a stale comment. |

Then, unless fixing is off (`--no-fix`, or config `code_review.fix: false`): **fix each one directly
in the worktree**, P0 first. You are not writing a report for someone else to action — the fix is the
deliverable, and an unfixed P0 that was merely described is a failed review.

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
review: <level> · scope <working|branch> · <repos> · angles <n> · agents <n> (deep <a> / light <b>)
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

**Hard cap: 50 lines, one line per finding.** This is read in a chat window by someone who is about
to commit; a wall of text gets skimmed, and that is how a P0 line goes unread.

- one line per finding, ≤ 200 characters — no sub-bullets, no code blocks, no restated diff hunks;
- **Fixed**: every P0 and P1 gets its own line; P2s beyond the eighth collapse into one rollup line
  (`+6 more P2 — reuse ×3, stale comment ×2, dead code ×1`);
- **Skipped**: 8 lines at most, the rest as `+<n> more skipped (<reason in three words>)`;
- **Needs you** is never capped, never merged and never rolled up — up to 3 lines each. It is the one
  block the user must act on, so it is the one block allowed to push the report past 50 lines.

Empty sections are omitted. Nothing found anywhere ⇒ the whole report is the header plus one line
saying the change is clean at this level — that is a good outcome, not a failure, and padding it with
P2s you don't believe in is worse than saying nothing.

### `--comment` — one summary on the PR

**Resolve this from the config, not from what the caller remembered to type.** With `--scope branch`,
comment when `code_review.final_comment` is `true`; `--no-comment` forces it off. With
`--scope working`, never — the per-iteration gate doesn't comment.

Post the report — minus the **Needs you** block, which belongs in chat — as a single comment, under
the same 50-line cap, through the feedback script so it carries the agent marker:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/pr_feedback.py" \
        reply --issue --cwd "$WT" [--pr <url>] --body-file <file>
```

**Never** post it with a bare `gh pr comment`. Without the marker the next iteration picks your own
review up as unaddressed reviewer feedback and starts answering itself.

## Red flags — STOP, you're breaking the contract
- Reviewing `git diff HEAD` alone → no. Committed-but-unpushed work and untracked files are part of the scope (Phase 0) and are where the newest code lives.
- A finder or verifier that edited a file → no. They run on `feature:review-finder`, which has no Edit/Write; if you fell back to `general-purpose`, Phase 4.5 is how you catch it.
- Dispatching an agent without a `model` → no. The default puts retrieval work on the deep tier, roughly doubling the run for the same bugs (see the tier table).
- Multiplying the angle budget by the number of repos → no. The budget is for the whole run; the split rule is the only exception, and it has a hard cap of 16.
- Finishing a run in which no verifier and no sweep agent ever ran → no. Fixes applied to unverified candidates aren't a review, they're an unreviewed rewrite.
- Reporting a P0 instead of fixing it (when fixing is on) → no. The fix is the deliverable.
- A finding that appears in neither Fixed, Skipped nor Needs you → no. Every survivor is accounted for.
- Refuting a candidate because it "depends on runtime state" → no. That's PLAUSIBLE; REFUTED needs a quoted line.
- Running a build, typecheck or test suite to produce findings → no. CI owns that signal.
- Flagging a CLAUDE.md or instructions violation without quoting the rule → no. Quote it or drop it.
- Skipping the PR comment on a pre-merge run because no `--comment` was passed → no. Read `final_comment` yourself.
- Posting the PR comment with `gh pr comment` → no. It must carry the marker (`pr_feedback.py reply --issue`).
- A report longer than 50 lines with an empty **Needs you** → no. Roll up the P2s.
- Committing, pushing or amending → no. The caller owns git.
- Saying "reviewed" after one inline pass when the Agent tool was available → no. The fan-out is the method, not a detail.
