# The review gate

An adversarial pass over the change in flight: it hunts correctness bugs first, then reuse,
simplification, efficiency, altitude and convention violations, **verifies every candidate before
believing it**, and fixes what survives. You get a cleaned diff and a one-line tally, not a list of
homework.

Everything on this page is configurable under [`code_review`](configuration.md#code_review) in
`<root>/.claude/feature/config.json`. Every default is chosen so that doing nothing is a reasonable
setup — read this when you want to spend less, look harder, or hunt something the built-in angles
don't.

---

## How it works

```
resolve the pass ──▶ build the diff pack ──▶ fan out angles ──▶ verify in batches
                                                                      │
   report ◀── fix in place ◀── triage ◀── cross-repo ◀── sweep ◀───────┘
```

Four properties are worth knowing, because the knobs below only make sense against them.

**It blocks.** The gate runs inline, in the agent's own turn. Nothing is committed, pushed or
answered while it is working. (An earlier version ran detached; a turn ended on the dispatch, the
next turn started a *second* review of the same worktree, and the change was pushed before either
reported.)

**Blindness sits at the leaves.** The agent orchestrating the review knows what the change was *for* —
the only way to tell a deliberate behavior change from a bug. The finders and verifiers it dispatches
get the diff and nothing else.

**The finders cannot write.** They run as `review-finder` / `review-finder-deep`, subagents with no
`Edit` and no `Write`. Fixing happens once, at the end, by the agent that called the gate.

**Two tiers.** Reasoning work (does this condition invert on an empty list?) runs on Opus; retrieval
work (quote the rule, read `git blame`, name the existing helper) runs on Sonnet. Roughly half the
cost of running everything deep, for the same bugs.

---

## When it runs — the run policy

The gate can fire at three moments, and each is switched and sized independently:

| Pass | When | Default |
|---|---|---|
| `first_iteration` | the iteration that opens the PR | on, `medium` |
| `later_iterations` | every iteration after that | on, `medium` |
| `final` | at finish, on the whole branch, after the base is merged in | on, `max`, posts a PR comment |

```json
"code_review": {
  "passes": {
    "first_iteration":  { "run": true, "level": "medium" },
    "later_iterations": { "run": true, "level": "medium" },
    "final":            { "run": true, "level": "max", "comment": true }
  }
}
```

The per-iteration passes are cheap on purpose: the `final` pass re-reviews all of that code at full
depth, on the integrated branch, before anything merges. **The `final` pass is the one not to cut.**
It is the only pass that ever sees the conflict resolutions — hand-written code, written under
pressure, that no per-iteration review could have seen because it didn't exist yet — and the only one
that can catch iteration 5 breaking an assumption iteration 1 relied on.

The switch is the config's, not the agent's. `run: false` and the skill stops with one line saying
which pass is off; the caller cannot argue it into running, and cannot argue it out.

> **Shorthand.** `working_level` sets the level of both per-iteration passes at once, and
> `final_pass` / `final_comment` are the older names for `passes.final.run` / `.comment`. They still
> work and are still the defaults that `passes` falls back to — use `passes` when the first iteration
> should differ from the later ones, or when you want one pass off.

---

## How hard it looks — levels

`level` is the ceiling for the whole gate. Every pass's level is clamped to it, so lowering that one
key lowers all three passes.

| Level | Angles | Sweep | Use when |
|---|---|---|---|
| `max` | up to 12 (5 deep) | yes | the pre-merge pass; anything about to merge |
| `high` | up to 10 | yes | same, minus the two PR-history angles |
| `medium` | 4 | no | per-iteration passes; fast feedback on work that gets reviewed again later |

The diff's own size collapses the budget below the ceiling on its own, so a small change never costs
a large review:

| Changed lines, all repos in scope | Deep agents | Light agents | Total |
|---|---|---|---|
| < 30 | 2 | 2 | 4 |
| 30–300 | 4 | 4 | 8 |
| > 300 | 5 | 7 | 12 |

The budget is for the **whole run**, not per repo — a second repo adds diff for the same agents to
read, not a second set of agents.

---

## How many agents — caps

| Key | Default | Caps |
|---|---|---|
| `max_finders` | `16` | agents in the find phase, including the per-repo split on large multi-repo changes |
| `max_verifiers` | `12` | agents in the verify phase |

Verification is batched by design — candidates grouped by file, up to four to an agent, correctness
apart from cleanup, except a suspected P0 which always gets a deep agent to itself. Lower these to
put a hard floor under the cost of a very large change; the gate degrades by merging angles and
enlarging batches, not by skipping work silently.

---

## What it looks for — angles

Each angle is a self-contained brief in its own file. The orchestrator never reads them — it hands
each finder a path — so adding angles costs leaf context, not the caller's.

| Angle | Tier | Hunts |
|---|---|---|
| `a-line-scan` | deep | every hunk, line by line |
| `b-removed-behavior` | deep | invariants the diff deleted and never re-established |
| `c-cross-file` | deep | call sites the change breaks |
| `d-language-pitfalls` | deep | this language's classic footguns |
| `e-wrapper-proxy` | deep | caches/proxies/adapters that route back through themselves |
| `altitude` | deep | bandaids that belong one level deeper |
| `reuse` | light | it already exists — names the helper to call instead |
| `simplification` | light | complexity the diff added |
| `efficiency` | light | work the diff wastes |
| `conventions` | light | violations of a rule it can quote, from `CLAUDE.md` or your standing instructions |
| `history` | light | changes that re-break something an earlier fix established |
| `prior-review` | light | points reviewers already made on these files (`max` only) |
| `code-comments` | light | comments the change violates, or turns into lies (`max` only) |

### Turn one off

```json
"code_review": { "angles": { "disabled": ["prior-review", "code-comments"] } }
```

### Rewrite one for this project

Drop a file at `<root>/.claude/feature/review-angles/<name>.md` using a built-in's name. It shadows
the shipped brief — no config entry needed, no fork of the plugin. Start from the shipped one:
`plugins/feature/skills/review/references/angles/<name>.md`.

### Add your own

```json
"code_review": {
  "angles": {
    "extra": [
      { "name": "a11y",         "tier": "light" },
      { "name": "query-budget", "tier": "deep"  }
    ]
  }
}
```

Then write `<root>/.claude/feature/review-angles/a11y.md`. The brief is plain markdown addressed to
the finder — say what class of defect to hunt, where to look, and what does *not* count. Keep it to
the shape of the shipped ones: they are the template.

```markdown
# Angle a11y — accessibility regressions · light

Flag changes that make the UI less usable without a mouse or without sight:

- an interactive element that is a `div` with an `onClick` and no role, `tabindex` or key handler
- an icon-only control that lost its accessible name
- a focus outline removed with no replacement
- a new dialog with no focus trap and no `aria-modal`

Only what this diff introduces. Report `repo/path:line` and quote the line.
```

Pick the tier by what the agent has to *do*: `deep` if it has to reason about behavior, `light` if it
mostly retrieves and matches. Unknown or missing tier ⇒ `light`.

A name listed in `extra` with no file anywhere is a hard error, with the path it looked for — the gate
refuses to run rather than quietly skip an angle you asked for.

Check what resolved:

```bash
python3 "<plugin>/skills/feature/scripts/config.py" --root "$ROOT" --review
```

It prints the gate as the skill will actually use it: the three passes, the caps, the models, and
every angle with its tier, its resolved path and whether that path is `builtin` or `user`.

---

## Cost, in one place

Roughly in order of effect:

1. **`passes.later_iterations.run: false`** — the biggest single saving on a long task. The `final`
   pass still covers everything those iterations wrote.
2. **`level`** — the ceiling. `high` drops the two PR-history angles; `medium` pins every pass to the
   4-agent row and skips the sweep.
3. **`light_agent_model`** — most agents are light-tier. Setting both models to `"opus"` roughly
   doubles the run; setting both to `"sonnet"` makes the correctness angles noticeably worse.
4. **`max_finders` / `max_verifiers`** — a hard floor under a very large change.
5. **`angles.disabled`** — drop what your project genuinely never hits.

## Recipes

| You want | Set |
|---|---|
| Review only at the end | `passes.first_iteration.run: false`, `passes.later_iterations.run: false` |
| Hard look at the first iteration, cheap after | `passes.first_iteration.level: "max"`, `later_iterations.level: "medium"` |
| Every iteration reviewed as hard as the merge | `passes.first_iteration.level: "max"`, `later_iterations.level: "max"` |
| Findings but no edits | `fix: false` |
| No PR comment at finish | `passes.final.comment: false` |
| Gate off entirely | `enabled: false` |
| Everything on Opus | `light_agent_model: "opus"` |
| Cap a huge change | `max_finders: 8`, `max_verifiers: 6` |

## What it never reports

Pre-existing issues the change didn't introduce; anything a linter, typechecker or CI already
catches; pedantic nits; issues the code explicitly silences; behavior changes that are plainly the
point of the task; missing tests or docs, unless one of your own quoted rules demands them.

It never commits, pushes or amends — the caller owns git.

## See also

- **[Configuration reference](configuration.md#code_review)** — every key, with defaults.
- **[The iteration workflow](workflow.md)** — where the three passes sit in the loop.
