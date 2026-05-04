#!/usr/bin/env python3
"""Print merged config (defaults + user override) for the systems-discover skill.

Reads:
  - <skill-dir>/defaults.json                         (built-in defaults)
  - <repo-root>/.claude/make-better.config.json       (optional user override)

Override file may be flat (applies to all skills) or have a "review" / "discover"
section. Common top-level keys are merged first, then the skill-specific section.

Output: pretty-printed JSON object with all knobs the skill needs. Exit code is
always 0 unless defaults.json is missing or unparseable (those are bugs).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SECTION = "discover"
SKILL_KEYS = {"review", "discover"}

skill_dir = Path(__file__).resolve().parent.parent
defaults = json.loads((skill_dir / "defaults.json").read_text())

try:
    repo_root = Path(
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    )
except (subprocess.CalledProcessError, FileNotFoundError):
    repo_root = Path(os.getcwd())

override_path = repo_root / ".claude" / "make-better.config.json"
override: dict = {}
if override_path.exists():
    try:
        user_cfg = json.loads(override_path.read_text())
    except json.JSONDecodeError as e:
        print(
            f"ERROR: {override_path} is not valid JSON: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(user_cfg, dict):
        print(
            f"ERROR: {override_path} must be a JSON object",
            file=sys.stderr,
        )
        sys.exit(1)
    common = {k: v for k, v in user_cfg.items() if k not in SKILL_KEYS}
    section = user_cfg.get(SECTION, {})
    if not isinstance(section, dict):
        print(
            f"ERROR: '{SECTION}' in {override_path} must be a JSON object",
            file=sys.stderr,
        )
        sys.exit(1)
    override = {**common, **section}


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


merged = deep_merge(defaults, override)
merged["_meta"] = {
    "skill": SECTION,
    "defaults_path": str(skill_dir / "defaults.json"),
    "override_path": str(override_path),
    "override_applied": override_path.exists(),
    "repo_root": str(repo_root),
}
print(json.dumps(merged, indent=2))
