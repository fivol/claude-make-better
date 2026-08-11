#!/usr/bin/env python3
"""Reaper for `feature` workspaces — keeps full-mode garbage from piling up.

Meant to run at the start of every agent turn (the skill calls it before doing
any work). It is cheap and self-throttling. Three jobs:

  1. Liveness   — drop dead dev_pids from .feature.json (local, no network).
  2. Server cap — keep at most --max live dev servers; evict the oldest
                  (LRU by .feature.json mtime). Eviction only STOPS the server
                  (kills its process group); the worktree/branch/PR stay, so the
                  next iteration can restart it on the same port.
  3. Teardown   — when ALL of a task's PRs are merged/closed, fully remove the
                  workspace: kill servers, `git worktree remove --force`, delete
                  the local branch, free ports, drop the proxy host, rm the dir.
                  This (networked) gh sweep is throttled to once per --sweep-age
                  seconds via <worktrees>/.reap.stamp, and time-boxed.

Tasks are discovered from BOTH <worktrees>/<task>/.feature.json (rich state) and
`git worktree list` (legacy worktrees with no state file). A task whose PR is
still OPEN, or that has no PR yet, is never touched — it may be in progress.

Usage (run from anywhere inside the workspace, or pass --root):
    reap.py [--root DIR] [--max N] [--sweep-age SECS] [--budget SECS]
            [--force-sweep] [--dry-run] [--verbose]
"""
import glob
import json
import os
import shutil
import signal
import subprocess
import sys
import time

import config

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PORTS_PY = os.path.join(SCRIPTS_DIR, "ports.py")
CADDY_PY = os.path.join(SCRIPTS_DIR, "caddyfile.py")


# ----------------------------------------------------------------- small utils
def log(msg):
    print(f"[reap] {msg}")


def vlog(opts, msg):
    if opts["verbose"]:
        log(msg)


def pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True  # exists, owned by someone else (shouldn't happen here)


def kill_group(pid, dry):
    """Kill the server's whole process group (pid == pgid thanks to serve.py)."""
    if not pid_alive(pid):
        return
    if dry:
        log(f"DRY would kill server group -{pid}")
        return
    try:
        os.killpg(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as exc:
        log(f"killpg {pid} failed: {exc}")


def run(cmd, cwd=None, timeout=20):
    try:
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


# ----------------------------------------------------------------- discovery
def discover(cfg):
    """Return {task: {dir, mtime, feature, repos:{repo:{wt,branch,dev_pid}}}}."""
    root = cfg["_root"]
    wtroot = config.worktrees_root(cfg)
    known_repos = config.repo_names(cfg)
    tasks = {}

    # 1. Rich state from .feature.json files.
    for fj in glob.glob(os.path.join(wtroot, "*", ".feature.json")):
        task_dir = os.path.dirname(fj)
        task = os.path.basename(task_dir)
        try:
            with open(fj) as f:
                feature = json.load(f)
        except (OSError, ValueError):
            feature = None
        entry = tasks.setdefault(
            task, {"dir": task_dir, "mtime": os.path.getmtime(fj),
                   "feature": feature, "repos": {}}
        )
        entry["feature"] = feature
        for repo, info in (feature or {}).get("repos", {}).items():
            entry["repos"][repo] = {
                "wt": os.path.join(task_dir, repo),
                "branch": info.get("branch") or config.branch_name(cfg, task),
                "dev_pid": info.get("dev_pid"),
            }

    # 2. Legacy worktrees with no state file — find them via git.
    for repo in known_repos:
        repo_dir = os.path.join(root, repo)
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            continue
        res = run(["git", "-C", repo_dir, "worktree", "list", "--porcelain"])
        if res.returncode != 0:
            continue
        wt_path = branch = None
        for line in res.stdout.splitlines() + [""]:
            if line.startswith("worktree "):
                wt_path = line[len("worktree "):]
            elif line.startswith("branch "):
                branch = line[len("branch "):].replace("refs/heads/", "")
            elif line == "":
                if wt_path and wt_path.startswith(wtroot + os.sep):
                    parts = os.path.relpath(wt_path, wtroot).split(os.sep)
                    if len(parts) == 2 and parts[1] == repo:
                        task = parts[0]
                        entry = tasks.setdefault(
                            task,
                            {"dir": os.path.join(wtroot, task),
                             "mtime": _safe_mtime(os.path.join(wtroot, task)),
                             "feature": None, "repos": {}},
                        )
                        entry["repos"].setdefault(
                            repo,
                            {"wt": wt_path, "branch": branch or config.branch_name(cfg, task),
                             "dev_pid": None},
                        )
                wt_path = branch = None
    return tasks


def _safe_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# ----------------------------------------------------------------- actions
def prune_dead_pids(cfg, tasks, opts):
    """Job 1 — clear dev_pids that no longer point at a live process."""
    for task, entry in tasks.items():
        feature = entry["feature"]
        if not feature:
            continue
        changed = False
        for repo, info in feature.get("repos", {}).items():
            pid = info.get("dev_pid")
            if pid and not pid_alive(pid):
                vlog(opts, f"{task}/{repo}: dev_pid {pid} dead → clearing")
                info["dev_pid"] = None
                entry["repos"].get(repo, {})["dev_pid"] = None
                changed = True
        if changed and not opts["dry_run"]:
            atomic_write_json(os.path.join(entry["dir"], ".feature.json"), feature)


def enforce_cap(cfg, tasks, teardown_set, opts):
    """Job 2 — keep at most --max live servers; evict the oldest beyond that."""
    live = []
    for task, entry in tasks.items():
        if task in teardown_set:
            continue
        mode = (entry["feature"] or {}).get("mode", "full")
        if mode in ("lite", "no-serve"):  # "no-serve" = legacy mode value
            continue
        if any(pid_alive(r.get("dev_pid")) for r in entry["repos"].values()):
            live.append((entry["mtime"], task, entry))
    if len(live) <= opts["max"]:
        return
    live.sort(key=lambda t: t[0])  # oldest first
    for _, task, entry in live[: len(live) - opts["max"]]:
        log(f"cap: evicting server for '{task}' (over --max={opts['max']})")
        feature = entry["feature"]
        for repo, info in (feature or {}).get("repos", {}).items():
            kill_group(info.get("dev_pid"), opts["dry_run"])
            info["dev_pid"] = None
        if feature and not opts["dry_run"]:
            atomic_write_json(os.path.join(entry["dir"], ".feature.json"), feature)


def pr_state(repo_info):
    """MERGED/CLOSED/OPEN for a repo's branch, or UNKNOWN if gh can't tell."""
    wt = repo_info["wt"]
    if not os.path.isdir(wt):
        return "UNKNOWN"
    res = run(
        ["gh", "pr", "view", repo_info["branch"], "--json", "state",
         "-q", ".state"],
        cwd=wt, timeout=15,
    )
    if res.returncode != 0:
        return "UNKNOWN"  # no PR yet, network error, etc. — stay safe
    return (res.stdout or "").strip().upper() or "UNKNOWN"


def teardown(cfg, task, entry, opts):
    """Job 3 — fully remove a finished workspace."""
    root = cfg["_root"]
    log(f"teardown: '{task}' (all PRs merged/closed)")
    if opts["dry_run"]:
        return True
    for repo, info in entry["repos"].items():
        kill_group(info.get("dev_pid"), opts["dry_run"])
        repo_dir = os.path.join(root, repo)
        if os.path.isdir(os.path.join(repo_dir, ".git")):
            run(["git", "-C", repo_dir, "worktree", "remove", "--force", info["wt"]])
            run(["git", "-C", repo_dir, "branch", "-D", info["branch"]])
            run(["git", "-C", repo_dir, "worktree", "prune"])
    run([sys.executable, PORTS_PY, "--root", root, "free", task])
    # `rm -rf` rather than shutil.rmtree: it never chokes on Next.js `.next`
    # build-cache files / symlinks the way rmtree(ignore_errors) silently does.
    run(["rm", "-rf", entry["dir"]])
    if os.path.exists(entry["dir"]):
        log(f"WARNING: '{task}' dir survived teardown: {entry['dir']}")
        return False
    return True


def sweep(cfg, tasks, opts):
    """Run the throttled, time-boxed PR-state teardown sweep. Returns set torn down."""
    torn = set()
    if not shutil.which("gh"):
        vlog(opts, "gh not found — skipping teardown sweep")
        return torn
    stamp = os.path.join(config.worktrees_root(cfg), ".reap.stamp")
    if not opts["force_sweep"]:
        age = time.time() - _safe_mtime(stamp) if os.path.exists(stamp) else 1e18
        if age < opts["sweep_age"]:
            vlog(opts, f"sweep throttled ({int(age)}s < {opts['sweep_age']}s)")
            return torn

    started = time.time()
    # Oldest workspaces first — they are the most likely to be done.
    for task in sorted(tasks, key=lambda t: tasks[t]["mtime"]):
        if time.time() - started > opts["budget"]:
            log("sweep budget reached — remaining tasks next sweep")
            break
        entry = tasks[task]
        if not entry["repos"]:
            continue
        states = [pr_state(info) for info in entry["repos"].values()]
        vlog(opts, f"{task}: PR states {states}")
        if states and all(s in ("MERGED", "CLOSED") for s in states):
            if teardown(cfg, task, entry, opts):
                torn.add(task)

    if not opts["dry_run"]:
        with open(stamp, "w") as f:
            f.write(time.strftime("%Y-%m-%dT%H:%M:%S\n"))
    return torn


# ----------------------------------------------------------------- main
def parse_opts(argv, cfg):
    opts = {
        "max": int(os.environ.get("FEATURE_MAX_SERVERS", cfg.get("max_live_servers", 5))),
        "sweep_age": int(os.environ.get("FEATURE_REAP_SWEEP_AGE", cfg.get("reap_sweep_age", 1800))),
        "budget": 60,
        "force_sweep": False,
        "dry_run": False,
        "verbose": False,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--max":
            opts["max"] = int(argv[i + 1]); i += 2; continue
        if a == "--sweep-age":
            opts["sweep_age"] = int(argv[i + 1]); i += 2; continue
        if a == "--budget":
            opts["budget"] = int(argv[i + 1]); i += 2; continue
        if a == "--force-sweep":
            opts["force_sweep"] = True; i += 1; continue
        if a in ("--dry-run", "-n"):
            opts["dry_run"] = True; i += 1; continue
        if a in ("--verbose", "-v"):
            opts["verbose"] = True; i += 1; continue
        if a in ("-h", "--help"):
            sys.exit(__doc__)
        sys.exit(f"reap.py: unknown arg '{a}'\n\n{__doc__}")
    return opts


def main():
    argv = sys.argv[1:]
    cfg = config.load(argv=argv)  # consumes --root
    opts = parse_opts(argv, cfg)
    root = cfg["_root"]
    if not os.path.isdir(config.worktrees_root(cfg)):
        vlog(opts, "no worktrees dir — nothing to reap")
        return

    tasks = discover(cfg)
    vlog(opts, f"discovered {len(tasks)} workspace(s)")

    prune_dead_pids(cfg, tasks, opts)
    torn = sweep(cfg, tasks, opts)
    # Re-discover so the cap sees post-teardown reality, then enforce it.
    tasks = discover(cfg)
    enforce_cap(cfg, tasks, torn, opts)

    if torn:
        # Ports/hosts changed — refresh the proxy (no-op if caddy isn't running).
        if not opts["dry_run"]:
            run([sys.executable, CADDY_PY, "--root", root, "--reload"])
        log(f"torn down: {', '.join(sorted(torn))}")


if __name__ == "__main__":
    main()
