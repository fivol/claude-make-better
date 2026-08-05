#!/usr/bin/env python3
"""Shared config loader for the `feature` skill scripts.

The skill operates on a *workspace root* — the directory that holds the
checkouts you build in (one or more git repos as sibling folders) plus the
`worktrees/` tree the skill creates. That root is NOT necessarily a git repo
itself (it is often a plain parent folder containing several repos), so we
cannot anchor it with `git rev-parse`. Instead the root is defined by the
presence of the per-project config file:

    <root>/.claude/feature/config.json

Resolution order for the root (first hit wins):
    1. --root DIR            (CLI flag, consumed from argv)
    2. $FEATURE_ROOT         (environment)
    3. nearest ancestor of CWD that contains .claude/feature/config.json
    4. nearest ancestor of CWD that contains a `worktrees/` dir or `.git`
    5. CWD

Config resolution:
    - <skill-dir>/defaults.json                  (built-in defaults, shipped)
    - <root>/.claude/feature/config.json         (per-project override)
  are deep-merged (override wins; lists are replaced wholesale, so a user
  `repos` list replaces the empty default).

Standing instructions (rules every iteration must follow) come from two places,
both optional and both always applied when present:
    - <root>/.claude/feature/INSTRUCTIONS.md     (free-form markdown)
    - config `instructions` / `repos[].instructions`  (arrays of strings)

This module is import-safe (no side effects) and also runnable:
    config.py [--root DIR]                        # merged config as JSON
    config.py [--root DIR] --instructions [--repos a,b]
                                                  # assembled instructions block
"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
DEFAULTS_PATH = os.path.join(SKILL_DIR, "defaults.json")

CONFIG_RELPATH = os.path.join(".claude", "feature", "config.json")
INSTRUCTIONS_RELPATH = os.path.join(".claude", "feature", "INSTRUCTIONS.md")


def take_value_arg(argv, flag):
    """Pop `<flag> VALUE` from argv (in place) and return VALUE, or None."""
    if flag in argv:
        i = argv.index(flag)
        try:
            value = argv[i + 1]
        except IndexError:
            sys.exit(f"config: {flag} needs an argument")
        del argv[i:i + 2]
        return value
    return None


def take_root_arg(argv):
    """Pop `--root DIR` from argv (in place) and return DIR, or None."""
    return take_value_arg(argv, "--root")


def _walk_up(start, predicate):
    d = os.path.abspath(start)
    while True:
        if predicate(d):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def resolve_root(argv=None, default_worktrees="worktrees"):
    """Resolve the workspace root. If argv is given, --root is popped from it."""
    if argv is not None:
        cli = take_root_arg(argv)
        if cli:
            return os.path.abspath(cli)
    env = os.environ.get("FEATURE_ROOT")
    if env:
        return os.path.abspath(env)
    cwd = os.getcwd()
    by_config = _walk_up(cwd, lambda d: os.path.isfile(os.path.join(d, CONFIG_RELPATH)))
    if by_config:
        return by_config
    by_marker = _walk_up(
        cwd,
        lambda d: os.path.isdir(os.path.join(d, default_worktrees))
        or os.path.isdir(os.path.join(d, ".git")),
    )
    if by_marker:
        return by_marker
    return cwd


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _require_str_list(value, where, path):
    """`instructions` is strictly an array of strings — no bare string shorthand."""
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        sys.exit(f"config: `{where}` in {path} must be an array of strings")


def _validate_instructions(cfg, path):
    _require_str_list(cfg.get("instructions", []), "instructions", path)
    for r in cfg.get("repos") or []:
        if isinstance(r, dict) and "instructions" in r:
            _require_str_list(
                r["instructions"], f"repos[{r.get('name', '?')}].instructions", path
            )


def load(root=None, argv=None):
    """Return the merged config dict. `root` resolved if not given.

    The returned dict always carries a private `_root` key with the resolved
    workspace root, so callers can pass the config around without re-resolving.
    """
    if root is None:
        root = resolve_root(argv)
    try:
        defaults = _read_json(DEFAULTS_PATH)
    except (OSError, ValueError) as e:
        sys.exit(f"config: cannot read defaults.json ({DEFAULTS_PATH}): {e}")

    override_path = os.path.join(root, CONFIG_RELPATH)
    merged = defaults
    if os.path.isfile(override_path):
        try:
            user = _read_json(override_path)
        except ValueError as e:
            sys.exit(f"config: {override_path} is not valid JSON: {e}")
        if not isinstance(user, dict):
            sys.exit(f"config: {override_path} must be a JSON object")
        merged = _deep_merge(defaults, user)

    _validate_instructions(merged, override_path)

    instructions_path = os.path.join(root, INSTRUCTIONS_RELPATH)
    merged["_root"] = root
    merged["_override_path"] = override_path
    merged["_override_applied"] = os.path.isfile(override_path)
    merged["_instructions_path"] = instructions_path
    merged["_instructions_applied"] = os.path.isfile(instructions_path)
    return merged


# --------------------------------------------------------------- accessors
def repos(cfg):
    """{name: repo_dict} from the config's repos list (order preserved in 3.7+)."""
    return {r["name"]: r for r in cfg.get("repos", []) if r.get("name")}


def repo_names(cfg):
    return [r["name"] for r in cfg.get("repos", []) if r.get("name")]


def worktrees_dir(cfg):
    return cfg.get("worktrees_dir", "worktrees")


def worktrees_root(cfg, root=None):
    return os.path.join(root or cfg["_root"], worktrees_dir(cfg))


def proxy(cfg):
    p = cfg.get("proxy") or {}
    return {
        "enabled": p.get("enabled", True),
        "domain_suffix": p.get("domain_suffix", "localhost"),
        "admin_host": p.get("admin_host", "admin.localhost"),
        "admin_port": int(p.get("admin_port", 7878)),
    }


def pr_feedback(cfg):
    """The `pr_feedback` block: how the PR's review comments are picked up/answered."""
    p = cfg.get("pr_feedback") or {}
    return {
        "enabled": p.get("enabled", True),
        "reply": p.get("reply", "always"),
        "resolve": p.get("resolve", "never"),
        "include_outdated": p.get("include_outdated", True),
        "include_bots": p.get("include_bots", False),
        "marker": p.get("marker", "<!-- feature:reply -->"),
    }


def primary_frontend(cfg, present):
    """The repo that owns the bare http://<task>.<suffix> alias.

    Walks the configured repo order and returns the first one that is both
    flagged `frontend: true` and present in `present` (an iterable of repo
    names in this task). Returns None if no configured frontend is present.
    """
    present = set(present)
    for r in cfg.get("repos", []):
        if r.get("frontend") and r.get("name") in present:
            return r["name"]
    return None


def frontend_sort_key(cfg):
    """Sort key putting frontends first, then config order, then name."""
    order = {name: i for i, name in enumerate(repo_names(cfg))}
    fe = {r["name"] for r in cfg.get("repos", []) if r.get("frontend")}

    def key(repo):
        return (repo not in fe, order.get(repo, 1 << 30), repo)

    return key


INSTRUCTIONS_HEADER = "=== PROJECT INSTRUCTIONS (standing rules — always follow) ==="


def instructions(cfg, repos_touched=None):
    """Assemble the standing-instructions block. Empty string when nothing is set.

    Sources, in order: the workspace `INSTRUCTIONS.md` (whole file, verbatim, whenever
    it exists), the config's top-level `instructions`, then each involved repo's
    `repos[].instructions`. `repos_touched` limits the per-repo sections to the repos an
    iteration actually touches; None ⇒ every configured repo.
    """
    root = cfg.get("_root") or ""
    path = cfg.get("_instructions_path") or os.path.join(root, INSTRUCTIONS_RELPATH)
    blocks = []

    if os.path.isfile(path):
        try:
            with open(path) as f:
                text = f.read().strip()
        except OSError as e:
            sys.exit(f"config: cannot read {path}: {e}")
        if text:
            label = os.path.relpath(path, root) if root else path
            blocks.append(f"--- {label} ---\n{text}")

    def bullets(rules):
        return "\n".join(f"- {r}" for r in rules if r.strip())

    workspace = bullets(cfg.get("instructions") or [])
    if workspace:
        blocks.append("--- config: instructions ---\n" + workspace)

    wanted = set(repos_touched) if repos_touched is not None else None
    for r in cfg.get("repos") or []:
        name = r.get("name")
        if not name or (wanted is not None and name not in wanted):
            continue
        rules = bullets(r.get("instructions") or [])
        if rules:
            blocks.append(f"--- config: repos[{name}].instructions ---\n" + rules)

    return f"{INSTRUCTIONS_HEADER}\n\n" + "\n\n".join(blocks) if blocks else ""


def main():
    argv = sys.argv[1:]
    repos_arg = take_value_arg(argv, "--repos")
    want_instructions = "--instructions" in argv
    if want_instructions:
        argv.remove("--instructions")
    cfg = load(argv=argv)
    if want_instructions:
        touched = [s.strip() for s in (repos_arg or "").split(",") if s.strip()]
        block = instructions(cfg, touched or None)
        if block:
            print(block)
        return
    print(json.dumps(cfg, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
