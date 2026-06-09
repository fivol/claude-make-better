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

This module is import-safe (no side effects) and also runnable:
    config.py [--root DIR]      # print the merged config as JSON
"""
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPTS_DIR)
DEFAULTS_PATH = os.path.join(SKILL_DIR, "defaults.json")

CONFIG_RELPATH = os.path.join(".claude", "feature", "config.json")


def take_root_arg(argv):
    """Pop `--root DIR` from argv (in place) and return DIR, or None."""
    if "--root" in argv:
        i = argv.index("--root")
        try:
            root = argv[i + 1]
        except IndexError:
            sys.exit("config: --root needs a directory argument")
        del argv[i:i + 2]
        return root
    return None


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

    merged["_root"] = root
    merged["_override_path"] = override_path
    merged["_override_applied"] = os.path.isfile(override_path)
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


def main():
    argv = sys.argv[1:]
    cfg = load(argv=argv)
    print(json.dumps(cfg, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
