# Phase 2 — Iteration

Runs on every prompt/edit once the workspace exists. Follow the order exactly; the chat summary is
produced **last**, after the change is already in the PR.

`WT="$ROOT/<worktrees>/<task>/<repo>"` for each involved repo. `ROOT` = the workspace root — anchor it
as in `workspace.md` (walk up to the `.claude/feature/config.json` marker), never `$(pwd)`.
`SCRIPTS="${CLAUDE_SKILL_DIR}/scripts"`.

## 0. Reap stale workspaces first

Before touching anything, prune finished/abandoned workspaces so dev servers and worktrees don't pile
up. The reaper is cheap and self-throttling — run it every turn:

```bash
python3 "$SCRIPTS/reap.py" --root "$ROOT"
```

It clears dead PIDs, keeps at most `max_live_servers` (config; default 5) live servers (evicting the
oldest — its worktree/PR stay, only the process is stopped), and — at most once per `reap_sweep_age`
(default 30 min) — fully tears down any workspace whose PR(s) are **all** merged/closed. Workspaces
with an OPEN or not-yet-created PR are never touched. If reap evicted *this* task's server, just
restart it (workspace.md §6) before you hand out URLs. Harmless in `--lite` mode too.

## 1. Implement

Make the requested change(s) inside the worktree(s). Never touch the main checkouts or base branches.

**Read every target file before you `Edit` it.** `Edit`/`Write` require a prior `Read` of that file
*in this session* — editing unread files is the single largest error class. When you're about to touch
several files, `Read` them all first, then edit. A worktree file you created earlier in another session
still needs a fresh `Read` here.

## 2. Simplify — MANDATORY after a significant change

Invoke the `/simplify` skill (a **real** Skill invocation — not just saying you will) scoped to the
files you changed this iteration. It cleans up reuse/duplication/dead code/readability — it does not
hunt for bugs and must not alter behavior. Any edits it makes are part of this iteration's commit.
(If `/simplify` is not installed, do an equivalent manual cleanup pass and say so.)

**Significant ⇒ required. Minor ⇒ may skip.** This is the only allowed skip:

| Skip simplify (minor) | Run simplify (significant) |
|---|---|
| one-/few-line diff in 1 file, **no new or restructured logic** | adds or changes logic / control flow |
| a constant, copy/string, type, import, config value, comment, version bump | a new function/component/hook/endpoint |
| a pure revert | a refactor, or a change spanning multiple files |

When in doubt → run it. Then **declare the outcome** in the iteration summary (step 5): `simplify: ✓`
or `simplify: skipped (minor)`. Never omit it silently — a silent skip is a contract violation, not a
minor edit.

## 3. Commit + push — explicit git, per repo

Stage only the files you changed this iteration (leave anything unrelated untouched). Spell out git
explicitly — do not delegate to a commit utility command:

```bash
git -C "$WT" add <file> [<file> ...]
git -C "$WT" commit -m "<short imperative message, why-focused>"
# first push of the branch:
git -C "$WT" push -u origin "task-<task>"
# subsequent iterations:
git -C "$WT" push
```

## 4. Ensure the PR exists

The branch must be pushed first. On the **first** iteration create one PR per repo (`gh` infers the
repo from the worktree's remote), targeting that repo's `base_branch`:

```bash
( cd "$WT" && gh pr create --base <base_branch> --title "<title>" --body "<what + why + how to test>" )
( cd "$WT" && gh pr view --json url -q .url )   # capture → store in .feature.json ".repos.<repo>.pr"
```

Later iterations need nothing — the push already updated the open PR.

## 4b. Persist the summary + session (powers the admin dashboard)

Write two things into the workspace so the admin dashboard (`scripts/admin.py`, see
`references/admin.md`) can show this task richly even long after the chat scrolls away. Cheap, do it
every iteration:

**a) `<worktrees>/<task>/summary.md`** — overwrite each iteration with the task's *current* state
(cumulative "what's done", not just this turn's delta). Same content you're about to put in chat, in
this structure (the admin renders the headings and turns `- [ ]` into real, click-persisted
checkboxes). Write it in the user's language; this English template is just the shape:

```markdown
# <task>

_updated <YYYY-MM-DD HH:MM> · iteration <n> · <repos involved>_

## What's done
- <per-repo bullets of everything done so far>
- simplify: ✓            # or: skipped (minor)

## What to consider / risks
- <cleaner approach, uncovered scenarios, edge cases, what's easy to forget>

## What to test
- [ ] <concrete check the reviewer should click through>
- [ ] <another>

## Links
- PR <repo>: <url>
- Test: http://<task>.<suffix>/<affected-route>     # full mode; omit in --lite
```

**b) the Claude session id** — so the admin's "continue chat" is exact, not a best-effort guess. Stamp
the *current* session into state:

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

## 5. Chat output (now, and only now)

Respond in the user's language. Blocks in this order — **always end with the test links** so they are
the last thing the user sees and can click:

1. **What's done** — concise summary of this iteration's changes (per repo if multi-repo). End this
   block with the simplify status line: `simplify: ✓` or `simplify: skipped (minor)`.
2. **Recommendations / what to consider** — direction for the next iteration tied to this task: a
   cleaner/more correct approach, scenarios still uncovered, edge cases, and what's easy to forget
   (errors, empty/limit states, mobile, i18n, migrations, auth).
3. **🔗 Test links** — the LAST block of every iteration. A clean, clickable list of **full URLs that
   open exactly the page(s)/endpoint(s) this change touches** (deep links, not just the site root) so
   the user clicks and immediately sees the result. Output bare `http://…` URLs (they render clickable
   in the terminal), one per line with a short label.
   - *full mode:* pretty deep links, e.g. `http://<task>.<suffix>/<affected-route>`; for backend
     changes the API URL too, e.g. `http://<backend>.<task>.<suffix>/api/<endpoint>`. Add
     `http://localhost:<port>/…` as a fallback. (Servers are already up; if one died, restart per
     `workspace.md` §6 and `--reload` the proxy first.)
   - *`--lite` mode:* no app URLs — give how to verify instead (typecheck / build / unit test, or the
     key diff lines).
   - Always include the PR link(s) here so progress is visible on the host.

The next user prompt starts a new iteration → back to step 1.
