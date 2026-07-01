#!/usr/bin/env python3
"""meta-review helper — window resolution + log append. Stdlib only, no deps.

Two subcommands:

  plan    Resolve the review window from the per-project log (last reviewed_at,
          or now-<default-days> on first run), list candidate session files in
          scope, and surface still-open items from the previous run.

  record  Append one meta-review session record (read as JSON from stdin) as a
          single line to the JSONL log.

The model orchestrates everything else; this script only owns the parts that
must be deterministic and consistent run-to-run (date math, the log format,
project-dir resolution).
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys

HOME = os.path.expanduser("~")
PROJECTS_ROOT = os.path.join(HOME, ".claude", "projects")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d


def encode_cwd(cwd):
    """Claude Code names a project dir by replacing every non-alphanumeric
    char in the absolute cwd with '-'. e.g. /Users/x/My_app -> -Users-x-My-app."""
    return "".join(c if c.isalnum() else "-" for c in os.path.abspath(cwd))


def project_dir_for_cwd(cwd):
    """Resolve the ~/.claude/projects/<...> dir for a working directory.
    Try the deterministic encoding first; if that dir is absent, scan project
    dirs and match the `cwd` field recorded inside the newest session."""
    enc = os.path.join(PROJECTS_ROOT, encode_cwd(cwd))
    if os.path.isdir(enc):
        return enc
    target = os.path.abspath(cwd)
    for d in sorted(glob.glob(os.path.join(PROJECTS_ROOT, "*"))):
        if not os.path.isdir(d):
            continue
        sessions = sorted(glob.glob(os.path.join(d, "*.jsonl")),
                          key=os.path.getmtime, reverse=True)
        for s in sessions[:1]:
            try:
                with open(s, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f):
                        if i > 300:
                            break
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("cwd") == target:
                            return d
            except OSError:
                continue
    return enc  # best guess even if it doesn't exist yet


def scope_dirs(scope, cwd, project_dir):
    if scope == "all":
        return sorted(d for d in glob.glob(os.path.join(PROJECTS_ROOT, "*"))
                      if os.path.isdir(d))
    if scope == "project":
        return [project_dir or project_dir_for_cwd(cwd)]
    # otherwise scope is an explicit cwd/path to target
    return [project_dir_for_cwd(scope)]


def read_last_record(log_path):
    if not os.path.isfile(log_path):
        return None
    last = None
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None
    return last


def open_items_from(record):
    """Items from the previous run that were not resolved — so the next review
    can resurface them. Prefers explicit decisions; falls back to important
    findings without a terminal decision."""
    if not record:
        return []
    out = []
    decisions = record.get("decisions") or []
    resolved_terminal = {"applied", "dismissed"}
    for d in decisions:
        action = (d.get("action") or "").lower()
        if action and action not in resolved_terminal:
            out.append({
                "title": d.get("title") or d.get("finding_id") or "(untitled)",
                "severity": d.get("severity"),
                "last_action": action,
                "note": d.get("note"),
            })
    if not out:
        decided_titles = {(d.get("title") or "").strip() for d in decisions}
        for fnd in record.get("findings") or []:
            if (fnd.get("severity") or "").lower() == "important":
                title = (fnd.get("title") or "").strip()
                if title and title not in decided_titles:
                    out.append({"title": title, "severity": "important",
                                "last_action": "not-recorded", "note": None})
    return out


def list_sessions(dirs, since):
    files = []
    for d in dirs:
        for s in glob.glob(os.path.join(d, "*.jsonl")):
            try:
                mtime = dt.datetime.fromtimestamp(os.path.getmtime(s),
                                                  dt.timezone.utc)
            except OSError:
                continue
            if since and mtime < since:
                continue
            files.append({
                "path": s,
                "session_id": os.path.splitext(os.path.basename(s))[0],
                "project_dir": d,
                "mtime": iso(mtime),
            })
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


def cmd_plan(args):
    last = read_last_record(args.log)
    last_review_at = parse_iso((last or {}).get("reviewed_at"))
    now = now_utc()
    default_used = False
    if last_review_at and last_review_at < now:
        since = last_review_at
    else:
        since = now - dt.timedelta(days=args.default_days)
        default_used = True
    dirs = scope_dirs(args.scope, args.cwd, args.project_dir)
    sessions = list_sessions(dirs, since)
    out = {
        "log_path": os.path.abspath(args.log),
        "log_exists": os.path.isfile(args.log),
        "scope": args.scope,
        "project_dirs": dirs,
        "since": iso(since),
        "until": iso(now),
        "default_used": default_used,
        "default_days": args.default_days,
        "last_review_at": iso(last_review_at) if last_review_at else None,
        "session_count": len(sessions),
        "sessions": sessions,
        "open_items": open_items_from(last),
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_record(args):
    raw = sys.stdin.read()
    try:
        rec = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"record: stdin is not valid JSON: {e}\n")
        return 2
    if not isinstance(rec, dict):
        sys.stderr.write("record: expected a JSON object\n")
        return 2
    if not rec.get("reviewed_at"):
        rec["reviewed_at"] = iso(now_utc())
    rec.setdefault("schema", "meta-review/v1")
    rec.setdefault("findings", [])
    rec.setdefault("decisions", [])
    line = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    d = os.path.dirname(os.path.abspath(args.log))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(args.log, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    sys.stderr.write(f"record: appended 1 line to {os.path.abspath(args.log)} "
                     f"({len(rec.get('findings', []))} findings, "
                     f"{len(rec.get('decisions', []))} decisions)\n")
    return 0


def main():
    p = argparse.ArgumentParser(description="meta-review log + window helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("plan", help="resolve window + list sessions in scope")
    pp.add_argument("--log", default=".meta-review.jsonl")
    pp.add_argument("--cwd", default=os.getcwd())
    pp.add_argument("--scope", default="project",
                    help="'project' | 'all' | <path to another project's cwd>")
    pp.add_argument("--project-dir", default=None,
                    help="explicit ~/.claude/projects/<...> dir "
                         "(e.g. from meta-cc get_session_directory)")
    pp.add_argument("--default-days", type=int, default=7)
    pp.set_defaults(func=cmd_plan)

    pr = sub.add_parser("record", help="append a session record (JSON on stdin)")
    pr.add_argument("--log", default=".meta-review.jsonl")
    pr.set_defaults(func=cmd_record)

    args = p.parse_args()
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
