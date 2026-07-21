---
name: iteration
description: Land a code change as a reviewed pull request — simplify the diff, commit, push, open or update the PR, then hand back considerations (risks, edge cases, what to test) and test links. Use proactively when the user wants to ship / commit / open a PR for the current change, or to "iterate" on work that should land via a PR. Runs standalone on the current branch, and is the engine the `feature` skill invokes inside its worktrees. If Feature Mode is already active, `feature` drives this — don't self-invoke.
---

# Iteration — land a change as a reviewed PR

The disciplined per-change loop, and the **single source of truth** for it:

> implement → **simplify** → commit → push → **PR** → **considerations** → test links

The chat summary is produced **last**, after the change is already pushed and in the PR. Never lead
with the summary.

## The rule that governs considerations: act on it, don't note it

A nuance you can act on now, you act on now. The instant you notice one — an edge case, an
empty/error/limit state, a cleaner or more correct approach, an applicable cross-cutting dimension
that isn't satisfied — the default is to **fold it into this iteration's implementation, before you
commit.** Not next iteration, not a footnote.

The **Considerations** block (step 6) is the *residue of that triage* — only what you consciously
chose **not** to do, each with a one-line reason — never a parking lot for work you saw but skipped.
Listing a fix you could have made is not addressing it; "I saw it and mentioned it every iteration"
is not doing it.

**Triage each nuance the moment it surfaces:**
- **Do it now (default)** when it's in scope for this change, part of making what you just built
  correct/complete, and doesn't need a product decision — even if that means a slightly bigger diff.
- **Defer** (→ Considerations, *with a reason*) **only** when it genuinely (a) needs a user/product
  decision, (b) is out of the task's scope, (c) is a large separate effort, or (d) can't be acted on
  in this mode (e.g. a browser you can't drive here). The reason names *why not now*, not just *what*.

Borderline between do-now and defer → **do it now.** This rule governs both step 2b (cross-cutting
dimensions) and the step-6 Considerations block below.

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
3. **If an applicable dimension is unmet, satisfying it is part of this iteration** — an applicable
   dimension that fails is a defect in the change you're making, not a follow-up. Adapt the diff now,
   then mark it `✓`. It stays `⚠` *only* when you genuinely can't act on it here (needs a decision, or
   this mode can't drive it — e.g. Safari from `--lite`/standalone), and then it carries the reason.

**Declare a per-entry outcome** in the summary (step 6), one token each:
`considerations: mobile ✓ · rtl n/a · cross-browser ⚠ (Safari flex-gap, no browser here)` — `✓`
verified (including verified *after* the iteration adapted the change to satisfy it) · `n/a` not
applicable (one-word reason if non-obvious) · `⚠` applicable but you genuinely couldn't act on it here
— needs a decision or this mode can't verify it; **always with a reason**, and carried into
**Considerations**. `⚠` is the narrow exception, not an escape hatch: a dimension you can see is unmet
gets *fixed and marked `✓`*, never downgraded to a footnote. Never omit the line when the list is
non-empty; writing `✓` without actually checking, or `⚠` for something you could have fixed this
iteration, is a contract violation.

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
- considerations: mobile ✓ · rtl n/a · cross-browser ⚠   # omit only if the config list is empty

## Considerations / risks
- <only what you deliberately deferred, each with why — not work you could have done this iteration>

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
   (`simplify: ✓` / `simplify: skipped (minor)`) and, when the config's `considerations` list is
   non-empty, the considerations line (`considerations: mobile ✓ · rtl n/a · …`).
2. **Considerations** — the *residue after triage* (see "act on it, don't note it" above): only what
   you deliberately did **not** fold into this change, each with a one-line reason it was deferred
   (needs a decision / out of scope / large separate effort / can't act on it here). Anything you
   *could* have addressed now must already be in **What's done** — not parked here. If triage left
   nothing to defer, say so in a line; an empty block is a success signal, not a gap to fill.
3. **🔗 Test / verify** — the LAST block.
   - *feature context:* clickable deep links that open exactly the affected page(s)/endpoint(s):
     `http://<task>.<suffix>/<affected-route>` (+ `http://localhost:<port>/…` fallback), API URLs for
     backend changes, and the PR link(s). Bare `http://…` per line with a short label. (If a server
     died, restart it and `--reload` the proxy first — see the `feature` skill.)
   - *standalone:* no app URLs — give how to verify (typecheck / build / unit test, or the key diff
     lines) + the PR link(s).

The next user prompt starts a new iteration → back to step 1.

## Red flags — STOP, you're about to break the contract
- "Too small to commit" → no. Every iteration commits (minor edits included).
- Said you'd simplify but didn't invoke `/simplify` → no. It must be a real skill invocation.
- Skipped the `considerations` line (non-empty config), or wrote `mobile ✓` without actually checking →
  no. Each applicable dimension must be really verified and reported (`✓`/`n/a`/`⚠`).
- Surfaced a nuance (edge case, cleaner approach, unmet dimension) and wrote it into **Considerations**
  instead of folding it into the diff → no. If you can act on it now, it belongs in the change, not
  the footnotes. Deferral is the exception and must name a real reason (needs a decision / out of scope
  / large separate effort / can't act here).
- Marked a dimension `⚠` for something you could have fixed this iteration → no. `⚠` is only "couldn't
  act on it here", with a reason; a dimension you can see is unmet gets fixed and marked `✓`.
- About to write the summary before pushing → no. Push first, summary last.
- About to commit onto a base/default branch → no. Feature context: use the `task-<task>` worktree
  branch. Standalone: branch off first.
- In feature context but skipping step 5 → no. summary.md + session stamp power the dashboard.
