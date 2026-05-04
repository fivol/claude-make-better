#!/usr/bin/env python3
"""Print merged config (defaults + user override) for the systems-review skill.

Reads:
  - <skill-dir>/defaults.json                          (built-in defaults)
  - <repo-root>/.claude/make-better/config.json        (optional user override)

Override file may be flat (applies to all skills) or have a "review" / "discover"
section. Common top-level keys are merged first, then the skill-specific section.

Topic prompt resolution:
  Each entry in topics_required + topics_optional is a name. The resolver looks
  for "<name>.md" first under <repo-root>/.claude/make-better/topics/, then
  under <skill-dir>/topics/. The first hit wins, so user files shadow built-ins
  with the same name. The merged JSON gets two extra fields:
    "_topics":             { "<name>": "<absolute path>", ... }
    "_unresolved_topics":  [ "<name>", ... ]   (empty when all topics resolved)

Output: pretty-printed JSON object. Exit code is 0 unless defaults.json or the
user override is malformed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SECTION = "review"
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

user_dir = repo_root / ".claude" / "make-better"
override_path = user_dir / "config.json"
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

user_topics_dir = user_dir / "topics"
plugin_topics_dir = skill_dir / "topics"
all_topic_names: list[str] = []
seen: set[str] = set()
for name in (merged.get("topics_required") or []) + (merged.get("topics_optional") or []):
    if name not in seen:
        all_topic_names.append(name)
        seen.add(name)

resolved_topics: dict[str, str] = {}
unresolved_topics: list[str] = []
for name in all_topic_names:
    user_file = user_topics_dir / f"{name}.md"
    plugin_file = plugin_topics_dir / f"{name}.md"
    if user_file.exists():
        resolved_topics[name] = str(user_file)
    elif plugin_file.exists():
        resolved_topics[name] = str(plugin_file)
    else:
        unresolved_topics.append(name)

merged["_topics"] = resolved_topics
merged["_unresolved_topics"] = unresolved_topics
merged["_meta"] = {
    "skill": SECTION,
    "defaults_path": str(skill_dir / "defaults.json"),
    "override_path": str(override_path),
    "override_applied": override_path.exists(),
    "user_topics_dir": str(user_topics_dir),
    "plugin_topics_dir": str(plugin_topics_dir),
    "repo_root": str(repo_root),
}
print(json.dumps(merged, indent=2))
