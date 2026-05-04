# Custom review topics

Out of the box, `/systems-review` audits each system across nine built-in topics:

- **bugs** — real defects in current code
- **completeness** — half-finished features, missing states, dead branches
- **dry** — duplicated logic to extract
- **architecture** — wrong-layer code, leaky abstractions, mis-placed responsibilities
- **consistency** — same thing done two different ways across the codebase
- **efficiency** — obvious perf wins, wasted work
- **tests** — missing coverage where it actually matters
- **docs-sync** — drift between code and docs/contracts
- **security** *(optional)* — surface-level vulnerabilities

You can add your own — domain-specific perf budgets, accessibility, i18n coverage, security policies, an internal style guide check, anything you want flagged on every review.

## How it works

For every name in `topics_required` ∪ `topics_optional`, the loader resolves a prompt file:

1. **`<repo-root>/.claude/make-better/topics/<name>.md`** — your custom prompt. Wins if present.
2. **`${plugin}/skills/systems-review/topics/<name>.md`** — built-in. Used when no user file exists.
3. **Neither found** → `/systems-review` aborts with: `Topic prompt(s) not found: ['<name>']. Create the file at .claude/make-better/topics/<name>.md or remove from topics_required/topics_optional.`

So you have two ways to use this:

- **Add a new topic** — give it a name that doesn't match any built-in.
- **Shadow a built-in** — give your file the same name as a built-in (e.g. `bugs.md`); your file takes over.

## Step-by-step: add a new topic

### 1. Create the prompt

Drop a file at `<repo-root>/.claude/make-better/topics/perf-budget.md`:

```markdown
---
name: perf-budget
required: true
---

# Perf Budget

## What to look for
- Functions with O(n²) work where n is unbounded user input.
- Synchronous calls in hot paths that could be batched or cached.
- Allocations inside tight loops.
- Re-renders in React components without memoization where the prop tree is deep.
- Database queries inside loops (N+1 pattern).

## What NOT to look for
- General optimization → handled by `efficiency`.
- Algorithmic redesigns → architecture.

## Output format
Return a JSON array. Each entry:

{
  "file": "path/to/file.ts",
  "line": 42,
  "issue": "short description of what's wrong",
  "severity": "high" | "medium" | "low",
  "fix": "what should change to address it"
}

Empty array if there's nothing to flag.
```

### 2. Register it in your config

`<repo-root>/.claude/make-better/config.json`:

```json
{
  "review": {
    "topics_required": [
      "bugs", "completeness", "dry", "architecture",
      "consistency", "efficiency", "tests", "docs-sync",
      "perf-budget"
    ],
    "topics_optional": ["security"]
  }
}
```

> **Note:** `topics_required` is **replaced** by your config (not merged element-wise). List every topic you want — both built-ins you keep and your additions.

### 3. Run

```
/systems-review
```

A topic agent is dispatched with your prompt for every reviewed system. Findings are folded into the consolidated plan alongside built-in topics.

## Shadowing a built-in

If `bugs.md` is too lax for your codebase (or you have a different idea of what counts as a "bug"), drop your version at `.claude/make-better/topics/bugs.md`. The loader will pick yours over the built-in. Use the [built-in `bugs.md`](../plugins/make-better/skills/systems-review/topics/bugs.md) as a starting point.

## Topic file structure

A topic prompt is a markdown file with optional YAML frontmatter:

```yaml
---
name: <topic-name>          # optional; informational only
required: <bool>            # optional; informational only
---
```

Below the frontmatter, write the prompt. The structure isn't enforced — agents are flexible — but the built-in topics all use this layout:

1. **`# <Topic name>`** — heading.
2. **`## What to look for`** — bullet list of things in scope.
3. **`## What NOT to look for`** — bullet list of things explicitly out of scope (helps the agent stay focused and avoid duplicate findings with other topics).
4. **`## Output format`** — JSON shape the topic agent must return. The standard shape is `[{ file, line, issue, severity, fix }, ...]` — stick to it unless you have a strong reason; the consolidated plan logic expects these fields.

The agent receives the prompt plus standard context (system's `areas:`, the relevant files, repo root, today's date). It runs read-only against the codebase and returns the JSON array.

## Examples to crib from

The built-in topics live at `plugins/make-better/skills/systems-review/topics/`:

- [`bugs.md`](../plugins/make-better/skills/systems-review/topics/bugs.md) — defect-finding
- [`dry.md`](../plugins/make-better/skills/systems-review/topics/dry.md) — duplicate-detection
- [`architecture.md`](../plugins/make-better/skills/systems-review/topics/architecture.md) — layering and responsibilities
- [`docs-sync.md`](../plugins/make-better/skills/systems-review/topics/docs-sync.md) — docs/code drift
- [`security.md`](../plugins/make-better/skills/systems-review/topics/security.md) — typical example of an optional, more conservative topic

Pick the one closest to what you're writing and adapt.

## Debugging

To verify a topic is being picked up:

```bash
cd /your/repo
bash $(find ~/.claude/plugins -path "*/make-better/skills/systems-review/bin/load-config.sh" | head -1) | jq '._topics, ._unresolved_topics'
```

Output:

```json
{
  "bugs": "/your/repo/.claude/make-better/topics/bugs.md",            ← shadowed built-in
  "dry": "/path/to/plugin/.../topics/dry.md",                          ← built-in
  "perf-budget": "/your/repo/.claude/make-better/topics/perf-budget.md" ← your custom topic
}
[]                                                                     ← no unresolved → all good
```

If a topic shows up under `_unresolved_topics`, the file isn't where the loader looked. Check the name (case-sensitive, must match exactly), and confirm the file is at `.claude/make-better/topics/<name>.md` from your repo root.

## When NOT to add a custom topic

A custom topic adds an extra agent dispatch per system per review run. The cost adds up. Consider whether you actually need a separate topic or whether your concern is already covered by a built-in:

- "Style nits" → built-in `consistency`.
- "Code organization" → built-in `architecture`.
- "Slow code" → built-in `efficiency` (use `perf-budget` only if you have specific quantitative budgets to enforce).
- "Missing tests" → built-in `tests`.
- "Missing docs" → built-in `docs-sync`.

Add a custom topic when you have a genuinely orthogonal concern that the built-ins won't catch — usually domain-specific or tied to your team's conventions.
