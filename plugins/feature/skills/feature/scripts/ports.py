#!/usr/bin/env python3
"""Deterministic per-workspace port allocator for the `feature` skill.

Registry lives at <root>/<worktrees_dir>/.ports.json and maps:
    { "<task>": { "<repo>": <port>, ... }, ... }

Each repo has its own base port band (from .claude/feature/config.json); a task
gets the smallest free offset in that band, so URLs stay stable across restarts
and never collide.

Usage (run from anywhere inside the workspace, or pass --root):
    ports.py alloc <task> <repo> [<repo> ...]   # print "repo=port" lines, persist
    ports.py get   <task>                         # print "repo=port" lines for a task
    ports.py free  <task>                         # release all ports of a task
    ports.py list                                 # dump the whole registry

Idempotent: alloc on an already-assigned (task, repo) returns the same port.
"""
import json
import os
import sys

import config


def registry_path(cfg):
    return os.path.join(config.worktrees_root(cfg), ".ports.json")


def load(cfg):
    path = registry_path(cfg)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save(cfg, data):
    path = registry_path(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def used_ports(data, repo):
    return {ports[repo] for ports in data.values() if repo in ports}


def alloc(cfg, task, repos):
    if not repos:
        sys.exit("alloc needs at least one repo")
    bands = {name: r.get("port_band") for name, r in config.repos(cfg).items()}
    data = load(cfg)
    task_ports = data.setdefault(task, {})
    out = []
    for repo in repos:
        if repo not in bands or bands[repo] is None:
            sys.exit(
                f"repo '{repo}' has no port_band in .claude/feature/config.json "
                f"(known: {', '.join(sorted(bands)) or 'none'})"
            )
        if repo in task_ports:  # idempotent
            out.append((repo, task_ports[repo]))
            continue
        base = int(bands[repo])
        taken = used_ports(data, repo)
        offset = 0
        while base + offset in taken:
            offset += 1
        port = base + offset
        task_ports[repo] = port
        out.append((repo, port))
    save(cfg, data)
    for repo, port in out:
        print(f"{repo}={port}")


def get(cfg, task):
    data = load(cfg)
    for repo, port in sorted(data.get(task, {}).items()):
        print(f"{repo}={port}")


def free(cfg, task):
    data = load(cfg)
    if task in data:
        del data[task]
        save(cfg, data)
    print(f"freed {task}")


def list_all(cfg):
    print(json.dumps(load(cfg), indent=2, sort_keys=True))


def main():
    args = sys.argv[1:]
    cfg = config.load(argv=args)
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "alloc":
        alloc(cfg, rest[0], rest[1:])
    elif cmd == "get":
        get(cfg, rest[0])
    elif cmd == "free":
        free(cfg, rest[0])
    elif cmd == "list":
        list_all(cfg)
    else:
        sys.exit(f"unknown command '{cmd}'\n\n{__doc__}")


if __name__ == "__main__":
    main()
