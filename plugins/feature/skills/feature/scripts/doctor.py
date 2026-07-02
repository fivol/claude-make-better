#!/usr/bin/env python3
"""Preflight for the `feature` skill — is everything needed actually in place?

Checks the toolchain and the workspace, and classifies every problem by who
should fix it:

    [agent]  the agent can and should do it now (create the config, `brew install gh`)
    [user]   only the user can (interactive login, a sudo/`:80` bind, cloning a repo)

Read-only: it runs `--version`/`auth status` probes and stats files — it changes
nothing, so it is safe to run anytime (including from the dashboard). The agent
runs this on entering Feature Mode, performs the [agent] fixes itself, and relays
the [user] actions to the user verbatim.

Usage:
    doctor.py [--root DIR] [--mode full|lite] [--json]

Exit code:
    0  ready, or only [agent]-fixable items remain (agent proceeds after fixing)
    1  at least one [user] action is required before building
    2  internal error
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
import config  # noqa: E402

PROXY_SETUP = os.path.join(SCRIPTS_DIR, "proxy-setup.sh")

OK, WARN, FAIL = "ok", "warn", "fail"
ICON = {OK: "✓", WARN: "⚠", FAIL: "✗"}


def _run(cmd, timeout=15):
    """Run a probe command; return (returncode, combined_output). 127 if absent."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, ""
    except Exception as e:  # pragma: no cover - defensive
        return 1, str(e)


def _r(key, label, status, detail="", owner="none", fix=""):
    return dict(key=key, label=label, status=status, detail=detail, owner=owner, fix=fix)


def check_tool(name, label, version_cmd, owner, fix):
    if not shutil.which(name):
        return _r(name, label, FAIL, "not installed", owner, fix)
    rc, out = _run(version_cmd)
    ver = out.splitlines()[0] if out else ""
    return _r(name, label, OK, ver)


def check_gh_auth():
    if not shutil.which("gh"):
        return None  # already reported by the gh-installed check
    rc, out = _run(["gh", "auth", "status"])
    if rc == 0:
        return _r("gh-auth", "gh auth", OK, "authenticated")
    return _r("gh-auth", "gh auth", FAIL, "not logged in", "user", "gh auth login")


def check_config(cfg):
    if cfg["_override_applied"]:
        return _r("config", "workspace config", OK, cfg["_override_path"])
    return _r(
        "config", "workspace config", FAIL,
        f"missing at {cfg['_override_path']}", "agent",
        "create .claude/feature/config.json (Phase 0 — references/workspace.md §0)",
    )


def _dep_hint(checkout, dep):
    d = dep.lower()
    if "node_modules" in d:
        how = "npm install (or pnpm/yarn/bun install)"
    elif d in ("venv", ".venv") or "venv" in d:
        how = "python3 -m venv " + dep + " && " + dep + "/bin/pip install -r requirements.txt"
    else:
        how = "produce it with the repo's usual install/build step"
    return f"in {checkout}: {how}"


def check_repos(cfg):
    out = []
    reps = config.repos(cfg)
    if cfg["_override_applied"] and not reps:
        out.append(_r("repos", "repos declared", WARN,
                      "config has no repos[] entries", "agent",
                      "add the repos you build in to config.json"))
    root = cfg["_root"]
    for name, r in reps.items():
        checkout = os.path.join(root, name)
        if not os.path.isdir(checkout):
            out.append(_r(f"repo:{name}", f"repo '{name}'", FAIL,
                          f"no checkout at {checkout}", "user",
                          f"clone the '{name}' repo into {checkout}"))
            continue
        if not os.path.isdir(os.path.join(checkout, ".git")):
            out.append(_r(f"repo:{name}", f"repo '{name}'", WARN,
                          f"{checkout} is not a git repo", "user",
                          f"make {checkout} the repo checkout (needs .git)"))
        else:
            out.append(_r(f"repo:{name}", f"repo '{name}'", OK, checkout))
        for dep in r.get("deps_symlink", []):
            if not os.path.exists(os.path.join(checkout, dep)):
                out.append(_r(f"deps:{name}:{dep}", f"'{name}' deps ({dep})", WARN,
                              f"{dep} missing in the main checkout", "user",
                              _dep_hint(checkout, dep)))
    return out


def _caddy_state(px):
    if not shutil.which("caddy"):
        return "absent"
    try:
        with urllib.request.urlopen("http://127.0.0.1:2019/config/", timeout=0.6) as resp:
            body = resp.read().decode("utf-8", "replace")
        return "serving" if px["admin_host"] in body else "running-unwired"
    except Exception:
        return "installed-down"


def check_caddy(cfg):
    """Optional (full mode only): pretty *.localhost URLs. Never blocking —
    localhost:<port> works without it. All remediation is the one sudo script."""
    px = config.proxy(cfg)
    setup = f'"{PROXY_SETUP}" (installs + starts Caddy on :80, sudo once)'
    state = _caddy_state(px)
    if state == "serving":
        return _r("caddy", "caddy (pretty URLs)", OK, f"serving {px['admin_host']}")
    detail = {
        "absent": "not installed",
        "installed-down": "installed but not running",
        "running-unwired": "running but workspace hosts not wired",
    }[state]
    return _r("caddy", "caddy (pretty URLs)", WARN,
              f"{detail} — localhost:<port> still works", "user", setup)


def collect(cfg, mode="full"):
    results = [
        check_tool("git", "git", ["git", "--version"], "user",
                   "install git (xcode-select --install, or brew install git)"),
        check_tool("gh", "gh (GitHub CLI)", ["gh", "--version"], "agent",
                   "brew install gh"),
    ]
    auth = check_gh_auth()
    if auth:
        results.append(auth)
    results.append(check_config(cfg))
    results.extend(check_repos(cfg))
    if mode == "full":
        results.append(check_caddy(cfg))
    return results


def render(cfg, mode, results):
    lines = [f"feature preflight — root: {cfg['_root']}   mode: {mode}"]
    for x in results:
        tag = f"   [{x['owner']}] → {x['fix']}" if x["owner"] in ("agent", "user") and x["fix"] else ""
        detail = f"  {x['detail']}" if x["detail"] else ""
        lines.append(f"  {ICON[x['status']]} {x['label']:<22}{detail}{tag}")
    user_blocks = [x for x in results if x["status"] == FAIL and x["owner"] == "user"]
    agent_todo = [x for x in results if x["status"] == FAIL and x["owner"] == "agent"]
    warns = [x for x in results if x["status"] == WARN and x["owner"] == "user"]
    lines.append("")
    if user_blocks:
        lines.append(f"Result: BLOCKED — {len(user_blocks)} user action(s) required before building "
                     "(the [user] lines above; relay them verbatim).")
    elif agent_todo:
        lines.append(f"Result: OK after agent setup — {len(agent_todo)} [agent] item(s) to do now, "
                     "then proceed.")
    else:
        lines.append("Result: OK — ready to build.")
    if warns:
        lines.append(f"(+{len(warns)} optional warning(s): dev-server deps / pretty URLs — "
                     "non-blocking, but tell the user how to enable them.)")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    mode = "full"
    if "--mode" in args:
        i = args.index("--mode")
        try:
            mode = args[i + 1]
        except IndexError:
            sys.exit("doctor: --mode needs full|lite")
        del args[i:i + 2]
        if mode not in ("full", "lite"):
            sys.exit("doctor: --mode must be 'full' or 'lite'")
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    try:
        cfg = config.load(argv=args)
        results = collect(cfg, mode)
    except SystemExit:
        raise
    except Exception as e:  # pragma: no cover - defensive
        print(f"doctor: internal error: {e}", file=sys.stderr)
        sys.exit(2)

    if as_json:
        print(json.dumps({"root": cfg["_root"], "mode": mode, "checks": results}, indent=2))
    else:
        print(render(cfg, mode, results))

    blocked = any(x["status"] == FAIL and x["owner"] == "user" for x in results)
    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
