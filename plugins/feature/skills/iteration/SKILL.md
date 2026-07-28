---
name: iteration
description: Land a code change as a reviewed pull request — simplify the diff, commit, push, open or update the PR, then hand back considerations (risks, edge cases, what to test) and test links. Use proactively when the user wants to ship / commit / open a PR for the current change, or to "iterate" on work that should land via a PR. Runs standalone on the current branch, and is the engine the `feature` skill invokes inside its worktrees. If Feature Mode is already active, `feature` drives this — don't self-invoke.
---

# Iteration — land a change as a reviewed PR

The disciplined per-change loop, and the **single source of truth** for it:

> implement → **simplify** → commit → push → **PR** → **considerations** → test links

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
   (`simplify: ✓` / `simplify: skipped (minor)`) and, when the config's `considerations` list is
   non-empty, the considerations line (`considerations: mobile ✓ · rtl n/a · …`).
2. **Considerations** — tied to this change: a cleaner/more correct approach, scenarios still
   uncovered, edge cases, and what's easy to forget (errors, empty/limit states, mobile, i18n,
   migrations, auth).
3. **🔗 Test / verify** — the LAST block.
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
- Reporting standing instructions as a per-item checklist → no. That's `considerations`; instructions
  are silent constraints.
- "Too small to commit" → no. Every iteration commits (minor edits included).
- Said you'd simplify but didn't invoke `/simplify` → no. It must be a real skill invocation.
- Skipped the `considerations` line (non-empty config), or wrote `mobile ✓` without actually checking →
  no. Each applicable dimension must be really verified and reported (`✓`/`n/a`/`⚠`).
- About to write the summary before pushing → no. Push first, summary last.
- About to commit onto a base/default branch → no. Feature context: use the `task-<task>` worktree
  branch. Standalone: branch off first.
- In feature context but skipping step 5 → no. summary.md + session stamp power the dashboard.
