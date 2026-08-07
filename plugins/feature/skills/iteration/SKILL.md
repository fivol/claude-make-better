---
name: iteration
description: Land a code change as a reviewed pull request — pick up the reviewer's unaddressed PR comments, simplify the diff, run the review gate that finds and fixes the change's own bugs, commit, push, open or update the PR, answer every comment, then hand back considerations (risks, edge cases, what to test) and test links. Use proactively when the user wants to ship / commit / open a PR for the current change, to "iterate" on work that should land via a PR, or to address review comments left on the PR. Runs standalone on the current branch, and is the engine the `feature` skill invokes inside its worktrees. If Feature Mode is already active, `feature` drives this — don't self-invoke.
---

# Iteration — land a change as a reviewed PR

The disciplined per-change loop, and the **single source of truth** for it:

> **pick up PR feedback** → implement → **simplify** → **review** → commit → push → **PR** →
> **answer the threads** → **considerations** → test links

The chat summary is produced **last**, after the change is already pushed and in the PR. Never lead
with the summary.

## Two ways this runs

Detect the mode once, at the start:

- **Feature context** — you're inside a `feature` task worktree: there is a
  `<worktrees>/<task>/.feature.json` for the checkout you're in, and the workspace has a
  `.claude/feature/config.json`. The `feature` skill invokes this contract here. Use the configured
  base branch per repo, span **all** involved repos, persist the dashboard artifacts, and hand out
  pretty URLs.
- **Standalone** — anything else (a plain repo/branch, you invoked me directly). Operate on the
  current git repo, PR into its default base branch, and give plain how-to-verify instead of pretty
  URLs. No worktree, no servers, no dashboard bookkeeping.

Read the feature config (works in both modes — it just returns defaults with no `repos` when there's
no workspace):

```bash
# ROOT = walk up from cwd to the dir holding .claude/feature/config.json; else the repo root
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT"
```

`_override_applied: true` **and** a `.feature.json` beside your checkout ⇒ feature context. Otherwise
standalone.

**Guard (standalone):** never commit straight onto a base/default branch. If `git branch --show-current`
is the default branch, create a topic branch first (`git switch -c <kebab-topic>`); then proceed. In
feature context the worktree is already on its `task-<task>` branch — just use it.

## The contract — in order

Let `WT` = the checkout you work in: each involved repo's worktree in feature context, or the current
repo in standalone. Run steps per involved repo.

### 0. Standing instructions — load them before you touch code
Project rules that hold for **every** iteration (stack conventions, what must never be touched, style
mandates). Assemble them once per iteration, before implementing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT" \
        --instructions --repos "<the repos you touch, comma-separated>"   # omit --repos standalone
```

Two sources, both optional, both applied **whenever present**: `<root>/.claude/feature/INSTRUCTIONS.md`
(free-form markdown, injected verbatim if the file exists) and the config's `instructions` +
`repos[].instructions` arrays (a repo's rules apply only when that repo is touched). Empty output ⇒
nothing configured ⇒ skip silently.

Treat every line as a **standing constraint on the work**, weighted like the user's own instructions:
obey it while implementing, simplifying, and committing. Unlike `considerations` (step 2b) they are
**not** a checklist — never report them per-item and never add an `instructions:` line to the summary.
If a rule and the user's explicit request for this iteration genuinely conflict, follow the user and
note the deviation in one line under **Considerations**.

### 0.5. Pick up the PR's review feedback — it belongs to this iteration
Unaddressed comments on the PR are work items, exactly like the user's prompt. Collect them **before**
implementing, so one iteration covers both (feature context: pass the repo's `pr` from `.feature.json`;
standalone: omit `--pr` and the branch's own PR is used):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/pr_feedback.py" list --cwd "$WT" [--pr <url>]
```

No PR yet, nothing unaddressed, or `pr_feedback.enabled: false` ⇒ one line of output and **skip
silently**. A `gh`/network failure (exit 2) is one line in the summary, never a blocker.

A thread is unaddressed when it is unresolved **and its last comment isn't yours**. Two traps the
script already handles — don't reintroduce them by hand: `gh` posts as the human's own account, so the
**author tells you nothing** (the marker in your own replies is the discriminator), and `isOutdated`
does **not** mean handled — a comment goes outdated the moment you push a fix touching that file. (On a
PR whose earlier replies predate the marker you may see a thread you already answered; the digest
prints the whole thread, so just don't answer it twice.)

Then act per item — do what's clear, ask only what genuinely isn't:

| Item | What you do |
|---|---|
| a concrete fix ("extract this into a helper") | implement it in this iteration |
| a question ("why like this?") | answer it in the thread; no code change |
| you disagree, or you see a better option | say so **with the argument** — never silently comply |
| out of scope for this task | don't widen the scope silently: answer where it belongs instead |
| genuinely ambiguous | ask it as a numbered question before implementing |

The user's chat prompt and the PR comments are **one** work list — deliver both. Never make the user
repeat a comment in chat because you didn't look.

### 1. Implement
Make the requested change(s) in `WT` only — never the main checkout or a base branch. **Read every
file before you `Edit` it** (Edit/Write require a prior Read this session; editing unread files is the
top error class). About to touch several files → Read them all first.

### 2. Simplify — MANDATORY after a significant change
Invoke the `/simplify` skill (a **real** Skill invocation, not a mention) scoped to the files you
changed this iteration. It cleans reuse/duplication/dead code/readability, must **not** change
behavior; its edits are part of this commit. (If `/simplify` isn't installed, do the equivalent manual
pass and say so.)

**Significant ⇒ required. Minor ⇒ may skip** (the only allowed skip):

| Skip (minor) | Run (significant) |
|---|---|
| one-/few-line diff in 1 file, **no new or restructured logic** | adds or changes logic / control flow |
| a constant, copy/string, type, import, config value, comment, version bump | a new function/component/hook/endpoint |
| a pure revert | a refactor, or a change spanning multiple files |

When in doubt → run it. Then **declare the outcome** in the summary: `simplify: ✓` or
`simplify: skipped (minor)`. Never omit it silently — a silent skip is a contract violation.

### 2b. Considerations — validate every applicable cross-cutting dimension
Read the config's `considerations` list — feature context:
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/config.py" --root "$ROOT"` → `.considerations`
(or read `.claude/feature/config.json`); standalone with no config ⇒ empty ⇒ **skip this step
silently**. Each entry is a recurring blind spot — something features get specified *without*
(desktop-only, LTR-only, Chrome-only) and that then ships broken. For each entry:

1. **Decide applicability** from its `when` (free-text condition) and optional `repos` (only applies
   when one of those repos is touched this iteration). Backend-only diffs usually make UI dimensions
   `n/a`.
2. For every **applicable** entry, *actually verify* the change satisfies its `check` — inspect the
   diff/layout, don't hand-wave. Full mode: open the pretty URL (emulate a mobile viewport, switch
   locale/RTL) to confirm; `--lite`/standalone: reason from the diff.

**Declare a per-entry outcome** in the summary (step 6), one token each:
`considerations: mobile ✓ · rtl n/a · cross-browser ⚠ (Safari flex-gap unchecked)` — `✓` verified ·
`n/a` not applicable (one-word reason if non-obvious) · `⚠` applicable but unverified / needs
follow-up (carry it into **Considerations**). Never omit the line when the list is non-empty; writing
`✓` without actually checking is a contract violation.

### 2c. Review — MANDATORY, and it is the last thing before the commit
`/simplify` improves code you wrote and whose intent you know. This step is the opposite on purpose:
an adversarial pass over the same diff, whose **finders never saw this conversation** and therefore
cannot excuse anything. It hunts correctness bugs first, then reuse/simplification/efficiency/
altitude/conventions, verifies each candidate before believing it, and **fixes what it finds**.

Invoke the `review` skill (a **real** Skill invocation, not a mention), after simplify and after
every code change of this iteration is on disk:

```
/feature:review --pass <first|later> --root "$ROOT" --repos "<the repos you touched>"
```

**`--pass first` when this iteration is opening the PR, `--pass later` on every one after it.** The
`.feature.json` entry for the repo tells you which: no `pr` recorded yet ⇒ `first`. That distinction
exists because the two are separately configurable — a project can review the first iteration deeply
and the later ones cheaply, or skip the later ones entirely and let the pre-merge pass carry them.
Getting the flag wrong silently applies the wrong policy, so read the state rather than guessing.

**Wait for it.** It is a gate, and it runs inline for exactly that reason: you do not commit, push,
answer the user or end your turn while it is still running. A turn that once ended on the dispatch
cost two full concurrent reviews of the same worktree and a push that landed before either of them
reported. If your turn is about to end and the review has not reported, the review has not run.

It reviews everything not yet in the PR — uncommitted work, commits made this iteration but not
pushed, and new untracked files — across **all** the repos you touched, so run it **once** for the
whole iteration, not once per repo. It never commits; its edits join this iteration's commit.

**Do not pass `--level`, and do not decide for yourself whether to run it.** The skill reads
`code_review.passes.<pass>` and applies that project's policy — including switching itself off and
saying so. `code_review.enabled: false` ⇒ it skips silently. `/feature:review` not installed ⇒ say so
in one line and carry on; never fake it.

**This covers the whole iteration's work, not just the chat prompt.** Code you wrote for the user's
request, code you wrote to satisfy a PR comment picked up in step 0.5, and anything you changed while
answering a reviewer are all in the same diff and all get reviewed. Never exclude "it was only a
review comment" from the gate — those changes are written under argument pressure and are exactly the
ones that skip a step.

The skill returns a compact report. **Do not paste it into the chat.** Take three things from it:

1. the status line for the summary — `review: ✓ max — fixed 4 (P0 1) · skipped 1`;
2. the **Needs you** items, if any — they are the one part the user must see, and they go into the
   chat as numbered questions (step 6, block 3). A `Needs you` item silently dropped is the worst
   failure mode of this step: it is a defect the reviewer found, could not decide alone, and nobody
   ever saw;
3. whether any fix touched a surface a `considerations` entry covers — if so, re-verify that entry
   before writing its `✓`.

Declare the outcome in the summary as `review: ✓ <level> — fixed <n> · skipped <m>`, or
`review: skipped (minor)`. Never omit it silently — a silent skip is a contract violation.

### 3. Commit + push — explicit git, per repo
Stage only the files you changed (leave unrelated files untouched). Spell out git explicitly — do not
delegate to a commit utility:

```bash
git -C "$WT" add <file> [<file> ...]
git -C "$WT" commit -m "<short imperative, why-focused>"
git -C "$WT" push -u origin "<branch>"    # first push of the branch
git -C "$WT" push                          # subsequent iterations
```

### 4. Ensure the PR exists
Branch must be pushed first. On the **first** iteration create one PR per repo (`gh` infers the repo
from the remote), targeting its base branch — configured `base_branch` in feature context, the repo's
default base standalone:

```bash
( cd "$WT" && gh pr create --base <base> --title "<title>" --body "<what + why + how to test>" )
( cd "$WT" && gh pr view --json url -q .url )
```

Later iterations need nothing — the push already updated the open PR.

### 4b. Answer on the PR — one reply per item you picked up
Only **after** the push, so the reply can cite the commit that settles it. Reply in the user's language
(config `output_language`), and be honest: agreement is a verdict, not a courtesy.

```bash
SC="${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/pr_feedback.py"
python3 "$SC" reply --thread <thread-id> --body "<verdict + what you did + <sha>>"
python3 "$SC" reply --issue --cwd "$WT" --to <item-url> --body "<answer>"   # review body / general comment
```

The script appends the agent marker — that's what makes the item count as answered next iteration —
so never hand-roll a reply with `gh api` / `gh pr comment`. A **thread** reply is self-addressing. A
**general** reply is not: it lands in the PR conversation with nothing tying it to what it answers,
so pass `--to <url of the review body or comment>` (the `url` field of the item in step 0.5's
output). Answering two review bodies ⇒ two `--to` replies, or one reply repeated per url — one
unaddressed `--to` means that item comes back next iteration, which is the safe direction to fail.

Resolving follows `pr_feedback.resolve` (default `never`: you answer, the reviewer resolves); under
`on_fix` / `always` resolve with `python3 "$SC" resolve --thread <id>`. Picked nothing up in step
0.5 ⇒ skip.

If step 0.5 printed a `!! GitHub capped …` line, the list was truncated by the API — say so in the
summary and open the PR to check the remainder by hand rather than reporting all feedback addressed.

### 5. Persist dashboard artifacts — **feature context only**
Skip entirely when standalone. Overwrite `<worktrees>/<task>/summary.md` with the task's *current*
cumulative state (what's done / considerations / what to test / links) in the user's language, using
the structure the admin dashboard renders (`- [ ]` become click-persisted checkboxes):

```markdown
# <task>

_updated <YYYY-MM-DD HH:MM> · iteration <n> · <repos involved>_

## What's done
- <per-repo bullets of everything so far>
- simplify: ✓            # or: skipped (minor)
- review: ✓ max — fixed 4 (P0 1) · skipped 1             # or: skipped (minor)
- considerations: mobile ✓ · rtl n/a · cross-browser ⚠   # omit only if the config list is empty
- feedback: 5 · fixed 3 · answered 1 · deferred 1        # omit when nothing was picked up

## Review feedback        # whole section omitted when nothing was picked up
- <path:line> «<short quote>» → <agreed / disagreed: why / better option: … / justified: …> · <what you did> (<sha>)

## Considerations / risks
- <cleaner approach, uncovered scenarios, edge cases, what's easy to forget>

## What to test
- [ ] <concrete check the reviewer clicks through>

## Links
- PR <repo>: <url>
- Test: http://<task>.<suffix>/<affected-route>
```

Then stamp the current session so the dashboard's "continue chat" is exact:

```bash
python3 - "$ROOT/<worktrees>/<task>/.feature.json" "$CLAUDE_CODE_SESSION_ID" <<'PY'
import json, sys
p, sid = sys.argv[1], sys.argv[2]
d = json.load(open(p))
if sid:
    d["session_id"] = sid
json.dump(d, open(p, "w"), indent=2)
open(p, "a").write("\n")
PY
```

Also store each repo's PR url into `.feature.json` `.repos.<repo>.pr` on first creation.

### 6. Chat output — now, and only now
Respond in the user's language. Blocks in this order, **ending with the test links** so they're the
last thing the user can click:

1. **What's done** — concise per-repo summary of this iteration. End with the simplify status line
   (`simplify: ✓` / `simplify: skipped (minor)`), the review status line
   (`review: ✓ max — fixed 4 (P0 1) · skipped 1`), the considerations line when the config's
   `considerations` list is non-empty (`considerations: mobile ✓ · rtl n/a · …`), and — when you picked
   feedback up in step 0.5 — the feedback line (`feedback: 5 · fixed 3 · answered 1 · deferred 1`).
2. **Review feedback** — omitted entirely when step 0.5 found nothing. One bullet per comment, each
   carrying three things: **where** (`path:line` + a short quote of the comment), **your honest
   verdict**, and **what you actually did**. The verdict is the point of this block — one of: agreed ·
   disagreed, with the argument · there's a better option, namely … · what's there is justified,
   because … Agreeing with everything is a smell, not politeness: if the reviewer is wrong, say why
   here and in the thread. This block is peer to the rest of the summary, not an appendix.
3. **Review — your call** — omitted entirely unless step 2c returned **Needs you** items. One
   numbered question each: where it is, what the reviewer found, and the two or more defensible
   options it wouldn't choose between. Nothing else from the review report belongs in chat — the
   status line in block 1 already says how much was fixed, and the fixes themselves are in the diff.
4. **Considerations** — tied to this change: a cleaner/more correct approach, scenarios still
   uncovered, edge cases, and what's easy to forget (errors, empty/limit states, mobile, i18n,
   migrations, auth).
5. **🔗 Test / verify** — the LAST block.
   - *feature context:* clickable deep links that open exactly the affected page(s)/endpoint(s):
     `http://<task>.<suffix>/<affected-route>` (+ `http://localhost:<port>/…` fallback), API URLs for
     backend changes, and the PR link(s). Bare `http://…` per line with a short label. (If a server
     died, restart it and `--reload` the proxy first — see the `feature` skill.)
   - *standalone:* no app URLs — give how to verify (typecheck / build / unit test, or the key diff
     lines) + the PR link(s).

The next user prompt starts a new iteration → back to step 1.

## Red flags — STOP, you're about to break the contract
- Implementing without loading the standing instructions (step 0) → no. They're constraints on the
  code you're about to write, so they're worthless read afterwards.
- Implementing while unaddressed PR comments sit on the PR → no. They're the same work list (step 0.5).
- Deciding a comment is handled because it's `isOutdated`, or because "the last comment is the author's"
  → no. Outdated means the file moved on; the author is the same account you post from.
- Answering a thread before the push → no. The reply has to cite the commit that settles it (step 4b).
- Writing "agreed" while leaving the code unchanged (or quietly fixing what you told the reviewer was
  fine) → no. The verdict and what you did must match, in the thread and in the summary.
- Reporting standing instructions as a per-item checklist → no. That's `considerations`; instructions
  are silent constraints.
- "Too small to commit" → no. Every iteration commits (minor edits included).
- Said you'd simplify but didn't invoke `/simplify` → no. It must be a real skill invocation.
- Committing without the review gate (step 2c) → no. Impartial review before the commit is the whole
  point; running it after the push reviews an empty diff, because the push already emptied the scope.
- Excluding the PR-comment work from the review because "it was only a comment" → no. Same iteration,
  same diff, same gate.
- Dropping a **Needs you** item from the review report → no. It's a found defect nobody decided on;
  it goes to the user as a numbered question (step 6, block 3).
- Pasting the whole review report into chat → no. The status line plus the `Needs you` questions is
  all that belongs there; the fixes are already in the diff.
- Reviewing your own change inline instead of invoking the skill → no. The gate's value is that the
  reviewer never saw this conversation and can't excuse anything.
- Skipped the `considerations` line (non-empty config), or wrote `mobile ✓` without actually checking →
  no. Each applicable dimension must be really verified and reported (`✓`/`n/a`/`⚠`).
- About to write the summary before pushing → no. Push first, summary last.
- About to commit onto a base/default branch → no. Feature context: use the `task-<task>` worktree
  branch. Standalone: branch off first.
- In feature context but skipping step 5 → no. summary.md + session stamp power the dashboard.
