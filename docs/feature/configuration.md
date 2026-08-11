# `feature` — configuration

The `feature` plugin is driven by one per-project file, with one optional companion:

```
<workspace-root>/.claude/feature/
├── config.json         # required — defines the workspace and its repos
├── INSTRUCTIONS.md     # optional — standing rules, injected whenever it exists
├── report.md           # optional — what the chat report contains
├── summary.md          # optional — what the dashboard card contains
└── review-angles/      # optional — your own review angles, or rewrites of the built-in ones
```

**Every policy the skills enforce is a key here**, with a shipped default — so you change behaviour in
config rather than forking a skill. Anything a *human reads* is a **template** instead: a file you
shadow, never prose you edit inside the plugin.

`config.json`'s **presence defines the workspace root** — the folder that holds your repo checkouts (each as a
sibling folder) and the `worktrees/` tree the skill creates. The scripts auto-resolve the root by
walking up from the current directory to the nearest ancestor containing this file (override with
`--root DIR` or the `FEATURE_ROOT` env var).

Values are deep-merged over the plugin's shipped `defaults.json` (override wins; lists are replaced
wholesale, so your `repos` list replaces the empty default).

## Full schema

```json
{
  "mode": "lite",
  "worktrees_dir": "worktrees",
  "max_live_servers": 5,
  "reap_sweep_age": 1800,
  "output_language": "the user's language",
  "instructions": [
    "Never add a dependency without asking first"
  ],
  "considerations": [
    {
      "name": "mobile",
      "when": "any change to UI / markup / styles in a frontend repo",
      "check": "Does this apply to the mobile viewport? If so, verify it's adapted: responsive layout, tap targets, no horizontal scroll, popups/modals fit.",
      "repos": ["web"]
    }
  ],
  "branch": { "prefix": "task-" },
  "simplify": { "enabled": true, "when": "significant" },
  "commit": { "per_pass": true, "message_language": "en" },
  "pr": { "enabled": true, "one_per": "repo", "draft": false },
  "merge": { "strategy": "merge", "via": "local-push", "wait_ci": true, "cleanup": true },
  "report": { "chat_template": null, "summary_template": null },
  "pr_feedback": {
    "enabled": true,
    "reply": "always",
    "resolve": "never"
  },
  "code_review": {
    "enabled": true,
    "level": "max",
    "working_level": "medium",
    "fix": true,
    "final_pass": true
  },
  "proxy": {
    "enabled": true,
    "domain_suffix": "localhost",
    "admin_host": "admin.localhost",
    "admin_port": 7878
  },
  "repos": [
    {
      "name": "api",
      "base_branch": "main",
      "port_band": 18000,
      "frontend": false,
      "deps_symlink": ["venv"],
      "env_copy": [".env"],
      "dev_start": "venv/bin/python manage.py runserver 0.0.0.0:{port}",
      "instructions": ["Every new endpoint needs a serializer test"]
    },
    {
      "name": "web",
      "base_branch": "main",
      "port_band": 13000,
      "frontend": true,
      "deps_symlink": ["node_modules"],
      "env_copy": [".env", ".env.local"],
      "dev_start": "node_modules/.bin/next dev -p {port}"
    }
  ]
}
```

## Top-level keys

| Key | Default | Meaning |
|---|---|---|
| `mode` | `"lite"` | `lite` — worktree + ship + PR, nothing to install beyond git/`gh`. `full` — also a unique port, a detached dev server, FE→BE wiring and a pretty `http://<task>.<suffix>` URL each pass. A `--lite`/`--full` flag from you overrides it for one session; the agent never infers it. |
| `worktrees_dir` | `"worktrees"` | Directory (under the root) for worktrees, the port registry, and the generated Caddyfile. |
| `max_live_servers` | `5` | Reaper cap on concurrent dev servers; the oldest beyond this are stopped (worktree/PR kept). |
| `reap_sweep_age` | `1800` | Min seconds between networked PR-state teardown sweeps (throttle). |
| `output_language` | `"the user's language"` | Hint for the language of agent output and the persisted `summary.md`. |
| `instructions` | `[]` | Standing rules every pass must obey — **strictly an array of strings** (see below). |
| `considerations` | `[]` | Cross-cutting dimensions the agent validates every pass (see below). Empty ⇒ feature off. |
| `branch` | `{"prefix": "task-"}` | Task-branch naming. `prefix` + the task slug, or a `template` with `{task}` for full control (`"feature/{task}"`). |
| `simplify` | see below | The `/simplify` cleanup gate. |
| `commit` | see below | Whether every pass commits, and the commit-message language. |
| `pr` | see below | Pull-request policy. |
| `merge` | see below | How a finished branch lands in its base. |
| `report` | see below | Where the output templates live, when not in the default locations. |
| `pr_feedback` | see below | How the reviewer's PR comments are picked up and answered each pass. On by default. |
| `code_review` | see below | The impartial review gate run before every commit and before the merge. On by default, at full depth. |
| `proxy` | see below | Pretty-URL / admin-dashboard settings. |
| `repos` | `[]` | The repos the skill can build in. **Required** for `workspace` — `ship`, `pr-feedback` and `merge` also run standalone on a plain repo with no config at all. |

## `simplify`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Run the `/simplify` gate on the files a pass changed. `false` ⇒ skipped silently, and nothing is reported. |
| `when` | `"significant"` | `significant` — skip one-/few-line edits with no new logic (constants, copy, imports, version bumps, pure reverts); `always` — every pass; `never` — same as `enabled: false`. |

The gate is quality-only: it must not change behavior, and its edits join the pass's commit. It needs
the `/simplify` skill installed; without it the agent does the equivalent manual pass and says so.

## `commit`

| Key | Default | Meaning |
|---|---|---|
| `per_pass` | `true` | Every pass commits, minor edits included. `false` ⇒ the work is left uncommitted and the report says so — for a workflow where you commit yourself. |
| `message_language` | `"en"` | Language of commit messages, independent of `output_language`. |

## `pr`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Open/update a PR at all. `false` ⇒ the branch is pushed and that's the end of the pass. |
| `one_per` | `"repo"` | `repo` — one PR per repo per task (the norm for multi-repo tasks). `task` — the primary repo carries the PR and the others are named in its body. |
| `draft` | `false` | Create PRs as drafts. |
| `title_template` | — | Override the PR title. Placeholders: `{task}`, `{repo}`, `{base}`, `{branch}`. |
| `body_template` | — | Override the PR body, same placeholders. |

## `merge`

| Key | Default | Meaning |
|---|---|---|
| `strategy` | `"merge"` | `merge` keeps the task SHAs, so pushing the base makes the host mark the PR merged by itself. `squash` / `rebase` rewrite them — required by repos with a squash-only policy, and then the host has to perform the merge. |
| `via` | `"local-push"` | `local-push` — merge locally and push the base (only valid with `strategy: merge`; your local base ends up current). `gh` — `gh pr merge` does it. Forced to `gh` for `squash`/`rebase`. |
| `wait_ci` | `true` | Wait for the PR's checks to go green before integrating. `false` for repos with no CI. |
| `cleanup` | `true` | After the merge: stop dev servers, remove the worktree, delete local+remote branches, free the port and the proxy host. |

Whatever the strategy, the base branch is always merged **into the task branch first**, with conflicts
resolved there — so the PR shows exactly what will land and CI runs on it.

## `report` — the output templates

What the agent *writes for a human* is a template, not prose inside a skill. Two of them:

| Template | Resolution order |
|---|---|
| the chat report | `report.chat_template` (path relative to the root) ▸ `.claude/feature/report.md` ▸ the plugin's default |
| the dashboard `summary.md` | `report.summary_template` ▸ `.claude/feature/summary.md` ▸ the plugin's default |

Drop a `report.md` next to your config and its blocks, order and status lines are what the agent
writes — no fork, no per-request reminder. See what is in force with:

```bash
python3 "<plugin>/scripts/config.py" --root . --report [--kind summary]
```

Keep report rules **out** of `INSTRUCTIONS.md`: those are loaded before the code is written and
weighted as constraints on the code, and by the time a long pass writes its report they are tens of
thousands of tokens away. The template is loaded at the moment the report is written, which is the
only time it is worth reading.

## `proxy`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Whether pretty `*.<suffix>` URLs are used (full mode). |
| `domain_suffix` | `"localhost"` | URL suffix. `*.localhost` resolves to `127.0.0.1` in Chrome with no DNS/hosts setup. |
| `admin_host` | `"admin.localhost"` | Hostname the admin dashboard is proxied at. |
| `admin_port` | `7878` | Port the admin dashboard listens on (also its `:127.0.0.1` fallback). |

## `pr_feedback`

Comments left on the PR are picked up as work items at the start of every pass and answered after
the push — see [PR review feedback](workflow.md#pr-review-feedback) for what the agent does with each
one. Nothing needs configuring: the defaults below are what ships.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Pick up PR comments at all. `false` ⇒ the step is skipped silently. |
| `reply` | `"always"` | `always` — answer every item; `on_fix` — reply only where code changed; `never` — act on comments but post nothing back. |
| `resolve` | `"never"` | `never` — the reviewer resolves threads (the open list stays your reading queue); `on_fix` — resolve the ones actually fixed; `always` — resolve everything answered. |
| `include_outdated` | `true` | Keep threads GitHub marks outdated. Usually the ones just worked on — a comment goes outdated the moment a fix touches that file. |
| `include_bots` | `false` | Also treat comments from `*[bot]` accounts (CodeRabbit, Dependabot…) as work items. |
| `marker` | `"<!-- feature:reply -->"` | Invisible tag the agent appends to its own replies — the only way to tell them apart, since `gh` posts under your account. Change it and previously answered threads resurface once. |

The agent's own PR comments count as feedback when they lack the marker — so any review write-up
posted to the PR by something else gets picked up and addressed on the next pass, exactly like a
human comment.

A review body or a general PR comment has no thread to reply into, so the agent's answer names what
it answers (`reply --issue --to <url>`) and the item counts as addressed only once some reply
references its url. Forgetting `--to` makes an item come back; nothing ever disappears because a
later comment happened to be newer.

## `code_review`

The review gate: an adversarial pass that finds the change's own bugs and fixes them, run at up to
three moments — the first pass, every later one, and once more on the whole branch before the
merge. On by default. Full guide, with recipes and custom angles: **[the review gate](review.md)**.

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Run the gate at all. `false` ⇒ every pass is skipped silently. |
| `level` | `"max"` | **Ceiling for the whole gate.** Every pass's level is clamped to it, so lowering this one key lowers all three. Angle budget: `max` — up to 12 angles (5 deep), sweep pass, recall-biased; `high` — 10, sweep; `medium` — 4, no sweep. The budget is for the whole run, not per repo, and the diff's size collapses angles below this ceiling on its own — so neither a small change nor a second repo costs you a larger review. |
| `passes` | see below | When the gate fires, and how hard, at each of the three moments. |
| `fix` | `true` | Apply what the review finds. `false` ⇒ it only reports, and you get a findings list instead of a cleaned diff. |
| `max_finders` | `16` | Hard cap on agents in the find phase. Over the cap the gate merges angles rather than dropping them silently. |
| `max_verifiers` | `12` | Hard cap on agents in the verify phase. Over the cap batches grow; a suspected P0 still gets an agent to itself. |
| `angles` | all 13 on | Which angles run, and where their briefs come from — see [angles](#code_reviewangles). |
| `deep_agent_model` | `"opus"` | Model for the agents that have to *reason*: the correctness angles, altitude, the cross-repo pass, and the verification of every P0 suspect. |
| `light_agent_model` | `"sonnet"` | Model for the agents that mostly *retrieve*: reuse, simplification, efficiency, conventions, git history, prior review comments, code comments, the sweep, and the verification of ordinary correctness and cleanup candidates. Set both to `"opus"` to run everything deep. |

Each tier is also a subagent type that declares its own model (`review-finder-deep`,
`review-finder`), so a dispatch that forgets the model still lands on the right tier instead of
silently running retrieval work on Opus.

### `code_review.passes`

Three moments, each with its own on/off switch and its own depth. This is the run policy, and it
belongs to the config: the agent does not get to decide per run whether a pass was worth it.

| Pass | Fires | `run` | `level` |
|---|---|---|---|
| `first_iteration` | the pass that opens the PR | `true` | `"medium"` |
| `later_iterations` | every pass after that | `true` | `"medium"` |
| `final` | at finish, on the whole branch, after the base is merged in | `true` | `"max"` |

`final` takes one extra key, `comment` (default `true`): post the pass's summary to the PR as one
marked comment, so it never comes back as reviewer feedback.

```json
"code_review": {
  "level": "max",
  "passes": {
    "first_iteration":  { "run": true,  "level": "max" },
    "later_iterations": { "run": false },
    "final":            { "run": true,  "level": "max", "comment": true }
  }
}
```

The per-pass runs are cheap by default because `final` re-reviews all of that code at full
depth before anything merges — the saving is in duplicated work, not in coverage. `final` is the one
not to cut: it is the only pass that sees the conflict resolutions, and the only one that can catch
pass 5 breaking an assumption pass 1 relied on.

**Shorthand.** `working_level` (default `"medium"`) sets the level of both per-pass runs at
once; `final_pass` and `final_comment` are the older names for `passes.final.run` and
`passes.final.comment`. All three still work, and are exactly the defaults `passes` falls back to —
reach for `passes` when the first pass should differ from the later ones, or when you want a
pass off.

### `code_review.angles`

| Key | Default | Meaning |
|---|---|---|
| `disabled` | `[]` | Names of built-in angles to drop. |
| `extra` | `[]` | Project-specific angles: `{"name": "a11y", "tier": "light"}`. Each needs a brief at `<root>/.claude/feature/review-angles/<name>.md`; a missing one is a hard error, not a silent skip. |

A file at `<root>/.claude/feature/review-angles/<name>.md` named after a **built-in** shadows the
shipped brief — that is how you rewrite an angle for one project without forking the plugin, and it
needs no config entry.

The thirteen built-ins, what each hunts, how to write your own, and what resolved for a given
workspace: **[the review gate → angles](review.md#what-it-looks-for--angles)**.

## `instructions[]`

**Standing rules** the agent follows on every pass — the project-wide equivalent of a
`CLAUDE.md`, scoped to feature work. Declare a rule once and it holds for every task in the
workspace, without you restating it per request.

Three sources, all optional, all applied **whenever present** — the `ship` skill assembles them
in its step 0, before any code is written:

| Source | Shape | Use it for |
|---|---|---|
| `instructions` in `config.json` | array of strings — strictly (a bare string is a config error) | short one-line rules, workspace-wide |
| `repos[].instructions` | array of strings | rules that apply only when that repo is touched |
| `.claude/feature/INSTRUCTIONS.md` | free-form markdown, injected verbatim | anything longer: prose, snippets, sections |

No config key points at `INSTRUCTIONS.md` and nothing switches it off: **if the file exists, it is
injected**. Delete it to stop applying it.

### instructions vs considerations

|  | `instructions` | `considerations` |
|---|---|---|
| What it is | a rule you follow | a check you re-run |
| When it applies | while writing the code | after the change, before commit |
| Reported back | never | every pass: `considerations: mobile ✓ · rtl n/a · …` |
| Example | "no `any` in TS" | "does this work on mobile?" |

Rule of thumb: if the answer is always the same and you'd never want it reported, it's an
instruction. If you have to look at the diff to answer, it's a consideration.

Example:

```json
"instructions": [
  "Never add a runtime dependency without asking first",
  "User-facing copy goes through i18n — no hard-coded strings"
],
"repos": [
  { "name": "web",
    "instructions": ["No `any` in TS", "Reuse the shared `Dropdown` — never write a new one"] }
]
```

### Checking what the agent will actually see

```bash
python3 <plugin>/skills/feature/scripts/config.py --root <workspace-root> --instructions --repos web
```

Prints the assembled block (file contents + config arrays, narrowed to the repos touched), or nothing
when none are configured.

## `considerations[]`

A checklist of **cross-cutting dimensions** the agent must validate on every pass, before
commit (the `ship` skill's contract, step 1b). These are the recurring blind spots —
things a feature gets specified *without* (desktop-only, LTR-only, Chrome-only, happy-path-only) and
that then ship broken. Declaring them once here means the agent reports an explicit
`considerations: mobile ✓ · rtl n/a · …` line every pass and can't silently forget them.

| Field | Required | Meaning |
|---|---|---|
| `name` | ✅ | Short label shown in the summary line (e.g. `mobile`, `rtl`, `cross-browser`, `a11y`). |
| `check` | ✅ | What to actually verify — phrased as an imperative the agent can act on, not just a topic. |
| `when` | — | Free-text applicability condition (e.g. "any UI/style change"). The agent decides per pass; omit ⇒ always considered applicable. |
| `repos` | — | Restrict applicability to passes that touch one of these repos (e.g. only frontends). Omit ⇒ any repo. |

Each pass the agent marks every applicable entry `✓` (verified), `n/a` (not applicable), or `⚠`
(applicable but unverified / needs follow-up). It's also a **self-improving** list: after `finish`,
the agent reviews the session and may propose new entries drawn from what bit this task — added only
with your approval (see `references/finish.md` §11).

Example:

```json
"considerations": [
  { "name": "mobile", "when": "any UI/markup/style change in a frontend repo",
    "check": "Verify the mobile viewport is adapted: responsive layout, tap targets, no horizontal scroll, popups fit.",
    "repos": ["web"] },
  { "name": "rtl", "when": "any UI text / layout change",
    "check": "If the app supports RTL locales, verify the layout mirrors correctly (no hard-coded left/right).",
    "repos": ["web"] },
  { "name": "cross-browser", "when": "non-trivial CSS / web-API usage",
    "check": "Sanity-check Safari/iOS for the change (flex gap, date inputs, sticky, backdrop-filter)." }
]
```

## `repos[]`

A repo's **checkout folder name must equal its `name`**, located directly under the workspace root.

| Field | Required | Meaning |
|---|---|---|
| `name` | ✅ | Repo / checkout folder name. |
| `base_branch` | ✅ | Branch to fork the task branch from and open the PR against (e.g. `main`, `dev`). |
| `port_band` | full mode | Base port for this repo; the allocator hands out the next free offset per task. Keep bands ≥1000 apart so parallel workspaces never collide across repos. |
| `frontend` | — | `true` ⇒ this repo owns the bare `http://<task>.<suffix>` alias. The first `frontend: true` repo present in a task wins; others get `http://<repo>.<task>.<suffix>`. |
| `deps_symlink` | — | Directories symlinked from the main checkout into the worktree (e.g. `node_modules`, `venv`). Never list build caches (`.next`, `build`, `.turbo`) — those must be per-worktree. |
| `env_copy` | — | `.env*` files copied (not symlinked) into the worktree, so per-workspace overrides (port, FE→BE URL) don't mutate the main checkout. |
| `instructions` | — | Standing rules (array of strings) applied only on passes that touch this repo — see [`instructions[]`](#instructions). |
| `dev_start` | full mode | Dev-server command, run with the worktree as the working directory. `{port}` is substituted with the allocated port. Tokenized with shell-style splitting (no shell), so env-prefixed vars must go through `env` — e.g. `env PORT={port} BROWSER=none npm start`. |

### `dev_start` examples

| Stack | `dev_start` |
|---|---|
| Django | `venv/bin/python manage.py runserver 0.0.0.0:{port}` |
| Create React App | `env PORT={port} BROWSER=none DANGEROUSLY_DISABLE_HOST_CHECK=true npm start` |
| Next.js | `node_modules/.bin/next dev -p {port}` |
| Vite | `node_modules/.bin/vite --port {port}` |

## Inspecting the merged result

Ask the agent to inspect the merged config — it runs the skill's `config.py` and prints the result as
JSON, including the resolved `_root`, `_override_path`, and `_override_applied`. Handy when a setting
doesn't seem to apply: you'll see whether your file was picked up at all.

## Environment overrides

| Env var | Overrides |
|---|---|
| `FEATURE_ROOT` | Workspace root (skips the config-marker walk-up). |
| `FEATURE_MAX_SERVERS` | `max_live_servers` (reaper). |
| `FEATURE_REAP_SWEEP_AGE` | `reap_sweep_age` (reaper). |
