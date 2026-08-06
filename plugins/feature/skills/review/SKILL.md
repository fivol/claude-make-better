---
name: review
description: Deep adversarial review of the change in flight — correctness bugs first, then reuse/simplification/efficiency/altitude/conventions, plus git history, prior review comments and cross-repo integration — every candidate independently verified, then fixed in place. Use before a change is committed, and again on the whole branch before it merges. The `iteration` skill invokes it as a mandatory gate; it also runs standalone on any repo. Not a style pass — for pure cleanup use `/simplify`.
---

# Review — find what's wrong with this change, then fix it

> gather scope → build the pack → find candidates → verify in batches → sweep → cross-repo → fix → report

Your job is not to produce a report the user reads and acts on. It is to **leave the tree better than
you found it** and hand back a short, honest account of what you changed, what you refused to change,
and what only the user can decide.

## This skill runs inline, and that is the whole design

**Do not run this skill in a fork, a background agent, or anything else that returns before the
review is done.** It is a gate: the caller must not be able to commit, push or answer the user while
it is still running. A detached run has already produced the worst failure this gate has had — the
caller ended its turn on the dispatch, the user asked why nothing happened, the next turn started a
*second* full fan-out over the same worktree, and the change was committed and pushed eight minutes
before either review returned. Two competing reviews, twenty-eight million tokens, and the gate's own
fixes landed as loose uncommitted work on top of the push.

So: you orchestrate **in this context**. Only the leaf agents are separate, and they are separate for
a reason that has nothing to do with hiding latency — see below.

**Blindness belongs at the leaves, not at the root.** The finders and verifiers see the diff and
nothing else: not the task, not the chat, not the author's reasoning. That is what makes their
judgement worth having. You are not blind, and that is deliberate too — you know what the change was
*for*, which is the only way to tell a deliberate behavior change from a bug, and the one call the
finders provably cannot make. What you must never do is defend the code. When a candidate lands,
read the line as if a stranger wrote it.

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
| `--level` | `--scope working` → config `code_review.working_level` (`medium`) · `--scope branch` → config `code_review.level` (`max`) | Angle budget — see Phase 1. |
| `--no-fix` | config `code_review.fix` (`true` ⇒ fix) | Report only, change nothing. |
| `--comment` / `--no-comment` | `--scope branch` → config `code_review.final_comment` (`true`) · `--scope working` → off | Also post one summary comment to the PR. |

**Flags are overrides, never prerequisites.** Every default above comes from the config, so a caller
that passes nothing — or that describes the scope in prose — still gets the configured behavior. A
behavior that only happens when the caller remembers a flag is a behavior that doesn't happen.

**The two passes are not the same depth, and that is deliberate.** The per-iteration pass
(`--scope working`) runs at `working_level` — cheap, because the same code is reviewed again, in
full, by the pre-merge pass once the branch is complete. The pre-merge pass (`--scope branch`) runs
at `level` and is the one that must not be cut: it is the only pass that sees the whole change, the
merged base and the conflict resolutions. `working_level` is clamped to `level`, so lowering the
ceiling lowers both. Resolve the level **before** Phase 1 and say which one you used in the report
header.

Read the config once — it also carries the project's standing rules, which are review criteria.
`ROOT` is the `--root` you were given; without one, drop the flag and let `config.py` resolve the
workspace root from cwd:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT"
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT" --instructions --repos "<repos>"
```

`code_review.enabled: false` ⇒ print one line and stop. No repo has a non-empty diff ⇒ same.

## The fan-out — read-only agents, on two model tiers

Every agent this skill spawns in Phases 1–4 is **read-only**, and every one carries its tier in the
subagent type it is dispatched as:

```
Agent(subagent_type: "feature:review-finder-deep", model: "<deep_agent_model>",  prompt: "<the brief>")
Agent(subagent_type: "feature:review-finder",      model: "<light_agent_model>", prompt: "<the brief>")
```

Both have **no `Edit` and no `Write`** — structural, not a request in a prompt. A finder that
"helpfully" fixes what it found writes code no one reviewed into a diff the caller is about to
commit, and it has already shipped regressions here. Finding is theirs; fixing is Phase 5's, and
Phase 5 is yours.

**The tier is structural too**: each type declares its own model, so a dispatch that forgets `model`
still lands on the right tier. Pass `model` anyway — it is what makes the config's
`deep_agent_model` / `light_agent_model` apply — but the type is what the run's cost rests on.
Sending every angle to one type was the single largest cost overrun this gate has had.

The split is by **what the agent must actually do**, not by how much the finding matters. Deciding
whether a condition inverts on an empty list is reasoning. Quoting a rule out of a `CLAUDE.md`,
reading `git log -L` output, filtering `gh api` results or naming the helper that already exists is
retrieval — and running retrieval deep roughly doubles the run for the same bugs.

Type doesn't resolve ⇒ retry the bare `review-finder-deep` / `review-finder`; still failing ⇒ fall
back to `general-purpose` with the read-only rule **and** the right `model` written into the prompt,
and say in the report that the finders ran unsandboxed. No Agent tool at all ⇒ do not error: work
every angle yourself, sequentially, in this context, and say so.

## Phase 0 — Resolve the scope

**Resolve from where you are, do not go looking.** `git -C . rev-parse --show-toplevel` and, in a
feature context, the `.feature.json` at or above it give you the worktree, the repos and each repo's
base branch directly. Only if cwd is outside any workspace do you fall back to scanning
`<root>/worktrees/`, and then **an ambiguous scan is a stop, not a guess**: more than one candidate
workspace ⇒ say which ones and ask. Picking "the one that happens to have a diff right now" reviews
whichever worktree someone else was last working in.

Per repo, `WT` = its worktree/checkout, `BASE` = its base branch.

### Build the diff pack — one command per repo

**Hand the finders paths, never instructions to re-derive the diff.** A dozen agents each rebuilding
the same diff with their own `git` calls and their own exploratory `ls` is the same work paid for a
dozen times, and the deep tier pays the most for it.

```bash
PACK="${TMPDIR:-/tmp}/feature-review-$(basename "$ROOT")-$$"
bash "${CLAUDE_PLUGIN_ROOT}/skills/review/scripts/pack.sh" \
     --wt "$WT" --repo "<repo>" --scope "<working|branch>" --base "$BASE" --out "$PACK"
```

It writes `<repo>.diff`, `.files`, `.log` and `.head`, and prints the one line you need next:

```
bitfront: 64 changed lines · 5 files · 2 commits · head d68f4cd9 · range @{upstream}..HEAD
```

The changed-line count is the input to the angle budget below — take it from here rather than
counting again. `.head` is not decoration: Phase 5 compares against it to catch a target that moved.

The script owns the parts that quietly go wrong by hand: it resolves the range for the scope
(including a branch that was never pushed, where the whole branch is unreviewed), it always adds the
uncommitted diff on top, and it inlines **every untracked file as an all-added hunk** — a brand-new
file is where the density of unreviewed logic is highest and is exactly what a plain `git diff`
misses. A pack built from one range alone silently narrows the review to less than the scope.

`0 changed lines` for a repo ⇒ that repo is out of scope; say so and move on. **Every repo empty ⇒
stop and say the scope was empty** — never invent a review of already-merged code.

The pack lives outside every repo, so it cannot dirty a worktree. Remove it when the run ends. If
`$TMPDIR` is unwritable, inline the diffs into the briefs instead and say so in the report, because
the run will cost noticeably more.

Test and fixture files are **in** scope, judged for wrong assertions, setup/teardown asymmetry and
cases the change silently stopped covering — not for style.

## Phase 1 — Find candidates

Run the angles below as **read-only subagents**, all dispatched in one message so they run
concurrently.

### The brief — three lines, plus the angle's own file

You do **not** read the angle files. Each one is a self-contained brief; you hand the finder its
path and it reads its own. That is what keeps this phase's cost in the leaves, where it belongs.

```
REPO <name> · worktree <WT>
Pack: <PACK>/<repo>.diff (<n> lines) · <PACK>/<repo>.files · <PACK>/<repo>.log
Read the diff from those files. Do NOT rebuild it with git.

Your job: read <SKILL_DIR>/references/angles/<file>.md and do exactly that, on this pack.
Return up to 8 candidates per repo, in the shape your agent definition specifies.
```

`<SKILL_DIR>` is `${CLAUDE_PLUGIN_ROOT}/skills/review` — resolve it to an absolute path before you
put it in a brief. A merged angle names both files and reports under both names.

Two angles need one extra line in the brief, and only those two: **Conventions** gets the assembled
standing instructions (the `--instructions` output above) pasted in, because it must quote them;
**Prior review** gets the PR URL or `owner/repo`.

### The candidate shape

The finders' own definition spells out the block they return: `repo` · `file` · `line` · `summary` ·
`failure_scenario` · `evidence` · `class` · `p0`. Three of those are yours to act on:

- **`class`** (correctness | cleanup) and **`p0`** route the candidate to its batch in Phase 2. They
  are not decoration.
- **`evidence`** — the lines the finder actually relied on, quoted — is what Phase 2 judges from, and
  what stops a verifier re-running the whole investigation from scratch. That has already made
  verification cost *more* than the search that fed it. A candidate with no evidence goes back to its
  finder, or to the verifier flagged as unevidenced.

Do NOT let one angle's conclusion suppress another's — if two angles flag the same line for
different reasons, record both. Pass through every candidate with a nameable failure scenario:
finders that silently drop half-believed candidates bypass the verify step, and that is the dominant
cause of misses. Dropping is Phase 2's job, not theirs.

Keep the agents' output out of your context beyond the candidates themselves. A finder that returns
prose gets read for its findings; the prose does not travel any further.

### The angle registry

| Angle | Tier | Brief |
|---|---|---|
| **A** — line-by-line diff scan | deep | `angles/a-line-scan.md` |
| **B** — removed-behavior auditor | deep | `angles/b-removed-behavior.md` |
| **C** — cross-file tracer | deep | `angles/c-cross-file.md` |
| **D** — language pitfalls | deep | `angles/d-language-pitfalls.md` |
| **E** — wrapper/proxy correctness | deep | `angles/e-wrapper-proxy.md` |
| **Altitude** — right depth, or a bandaid | deep | `angles/altitude.md` |
| **Reuse** — it already exists | light | `angles/reuse.md` |
| **Simplification** — complexity added | light | `angles/simplification.md` |
| **Efficiency** — work wasted | light | `angles/efficiency.md` |
| **Conventions** — quoted rule violations | light | `angles/conventions.md` |
| **History** — re-breaks an old fix | light | `angles/history.md` |
| **Prior review** — reviewers already said it (`max`) | light | `angles/prior-review.md` |
| **Code comments** — the change lies to them (`max`) | light | `angles/code-comments.md` |

### Angle budget — one budget for the whole run

Sum the changed-line counts `pack.sh` printed **across all repos in scope** and pick one row. That
number is the angle count for the **run**. The number of repos never multiplies it.

The **deep** column is what the row actually costs — a deep agent is roughly five times a light one,
so the rows cut deep agents first and leave the light angles alone.

| Changed lines, all repos | Deep agents | Light agents | Total |
|---|---|---|---|
| < 30 | A+B, C+D+E → **2** | Reuse+Simplification+Efficiency, Conventions → **2** | **4** |
| 30–300 | A+B, C, D+E, Altitude → **4** | Reuse, Simplification+Efficiency, Conventions, History → **4** | **8** |
| > 300 | A, B, C, D+E, Altitude → **5** | Reuse, Simplification, Efficiency, Conventions, History, Prior review, Code comments → **7** | **12** |

A merged angle is one agent running both briefs in one pass, reporting under both names — not one
brief standing in for the other. **A merged angle never mixes tiers**: every merge above is within a
tier, and the row's deep column is the whole deep budget.

**One agent per angle, covering every repo in scope.** Hand it all the repos' pack paths at once; it
returns candidates tagged by repo. The single exception: when **two or more repos each have > 300
changed lines**, the per-hunk angles (**A**, **B**, **C**) get one agent per repo — those are the
angles that must read every line, and attention does not divide. Apply the split to the largest
repos first and stop when you hit the cap.

**Hard cap: 16 finder agents per run.** Whatever the split suggests, you never dispatch more; drop
back toward one agent per angle until you fit. Say in the report which row you used and how many
agents ran, split by tier.

`--level high` drops the two `max`-only context angles (Prior review, Code comments) before applying
the table; `--level medium` uses the `< 30` row whatever the diff size, and skips Phase 3.

## Phase 2 — Verify, in batches

Dedup first: candidates pointing at the same line/mechanism collapse into one, keeping the most
concrete failure scenario and the union of their evidence.

Then **batch — one verifier agent per batch, not per candidate.** A verifier per candidate does not
survive contact with a real diff: 40 candidates means 40 agents, so the phase gets quietly skipped
and fixes land on unverified findings. Batching is what makes this phase actually run.

| Batch | Size | Tier |
|---|---|---|
| **P0 suspects** (`p0: yes`) | 1 — alone, always | deep |
| correctness candidates | group by file, **≤ 4** per batch | light |
| cleanup candidates | group by file, **≤ 4** per batch | light |

Only P0 suspects verify deep, and that is the safe direction: this phase can only **drop**
candidates, and it drops one only by quoting the line that disproves it. A lighter verifier that is
unsure keeps the candidate — the cost of that is one extra fix to consider in Phase 5, not a missed
bug. The candidates where a wrong drop is unaffordable are exactly the P0 suspects, and those still
get a deep agent to themselves.

Never mix classes in a batch. **Cap: 12 verifier agents** — over the cap, raise the non-P0 batch size
to 8; P0 suspects stay solo whatever happens. Dispatch every batch in one message.

The brief is the same three lines as Phase 1, plus:

```
Your job: read <SKILL_DIR>/references/verify.md and do exactly that.
Candidates, numbered — each with the evidence its finder quoted:
1. ...
```

Each verifier returns **one verdict per number, in order, and nothing else**. Fewer verdicts than
candidates is a failed run: re-dispatch the missing ones — never read a missing verdict as REFUTED.

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

One **light-tier** agent for the run, briefed with `<SKILL_DIR>/references/sweep.md` and handed the
verified list. (One per repo only when Phase 1's per-hunk split applied, i.e. 2+ repos over 300
changed lines each.) New candidates go through Phase 2 like the rest.

This phase is one cheap agent. Skipping it because the run already feels big is a silent downgrade of
the level the caller asked for — if you truly cannot run it, say so in the report header.

## Phase 4 — Cross-repo integration (feature context, 2+ repos) · deep

One subagent, briefed with `<SKILL_DIR>/references/cross-repo.md`, that sees **all** the repos' packs
at once. Its findings skip Phase 2 — there is no single line to refute — and go straight to triage as
P0/P1.

## Phase 5 — Triage, then fix

**First, check the target hasn't moved.** You have been running for minutes, and in a live workspace
that is long enough for the tree to change under you:

```bash
git -C "$WT" rev-parse HEAD | diff - "$PACK/<repo>.head"   # same commit the pack was cut from?
```

A different sha, or a working diff that no longer matches the pack, means the change was committed,
amended, rebased or rewritten while you reviewed. That is **not** an error and nothing gets reverted —
you are a reviewer, and the tree belongs to whoever is working in it. It only means your findings
were computed against a state that has moved on. Re-read the current state of each surviving
finding's lines before you fix anything, drop the ones the new state already resolved, and put one
line in the report saying the target moved.

Then rank what survived. Correctness always outranks cleanup, altitude and conventions.

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

This is also the one place an **experiment** belongs. A verifier that returned PLAUSIBLE because the
verdict needed a running app, a rendered page or a real request handed you that experiment on
purpose: you have the tools and the context to run it, and it is far cheaper here than as a read-only
agent guessing from the source.

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

Write it in the config's `output_language`. Findings are cited as `<repo>/<path>:<line>` so they stay
unambiguous across repos.

```
review: <level> · scope <working|branch> · <repos> · angles <n> · agents <n> (deep <a> / light <b>) · <m> min
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

The elapsed minutes are in the header because this gate blocks the caller, and a run that took
forty minutes on a sixty-line diff needs to be visible as such rather than discovered later.

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
- Returning to the caller before the review is done → no. This is a gate; a gate that doesn't block isn't one, and the caller will commit without it.
- Reviewing `git diff HEAD` alone → no. Committed-but-unpushed work and untracked files are part of the scope (Phase 0) and are where the newest code lives.
- Picking the worktree by "the one with a diff" → no. Resolve from cwd; an ambiguous scan is a question, not a guess.
- Reading the angle files yourself → no. You hand out their paths; they cost their own context, not yours.
- Sending every agent to one subagent type → no. The type carries the tier; using `-deep` for retrieval angles roughly doubles the run for the same bugs.
- A candidate with no quoted evidence → no. Without it the verifier re-runs the whole search and costs more than the finder did.
- Reverting someone else's edits because the tree changed mid-run → no. The finders cannot write; the tree belongs to whoever works in it. Re-read and re-check, never undo.
- Multiplying the angle budget by the number of repos → no. The budget is for the whole run; the split rule is the only exception, and it has a hard cap of 16.
- Finishing a run in which no verifier and no sweep agent ever ran → no. Fixes applied to unverified candidates aren't a review, they're an unreviewed rewrite.
- Reporting a P0 instead of fixing it (when fixing is on) → no. The fix is the deliverable.
- A finding that appears in neither Fixed, Skipped nor Needs you → no. Every survivor is accounted for.
- Refuting a candidate because it "depends on runtime state" → no. That's PLAUSIBLE; REFUTED needs a quoted line.
- Running a build, typecheck or test suite to produce findings → no. CI owns that signal.
- Flagging a CLAUDE.md or instructions violation without quoting the rule → no. Quote it or drop it.
- Posting the PR comment with `gh pr comment` → no. It must carry the marker (`pr_feedback.py reply --issue`).
- Committing, pushing or amending → no. The caller owns git.
