#!/usr/bin/env python3
"""Keep the admin dashboard running across logins (macOS launchd user agent).

The dashboard is only useful if it is up, and Caddy already proxies
`admin.localhost` to it — so it wants to be a service, not something you
remember to start. This installs it as a **user** LaunchAgent (no sudo, no root):

    ~/Library/LaunchAgents/com.fivol.feature-admin.plist  →  the launchd job
    ~/.claude/bin/feature-admin                           →  the wrapper it runs

The wrapper exists so a plugin upgrade doesn't break the job: when this script
lives under `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/…`, the
wrapper re-resolves the newest installed version at every launch instead of
pinning the one that happened to be current at install time.

Two details launchd gets wrong by default, both handled here:
  - its PATH has no Homebrew, so `gh` (PR state + CI) and `caddy` would be missing;
  - the workspace root isn't the cwd, so it is baked in as $FEATURE_ROOT
    (config.py resolution step 2).

Usage:
    autostart.py [--root DIR] --status [--json]
    autostart.py [--root DIR] --install
    autostart.py [--root DIR] --uninstall
    autostart.py [--root DIR] --decline      # remember "no", stop asking

Exit code (--status):
    0  installed and healthy
    1  not installed, or installed but degraded (see `advice`)
    2  unsupported platform / internal error
"""
import json
import os
import plistlib
import re
import shutil
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
import admin  # noqa: E402  — reuse the dashboard's own liveness probe
import config  # noqa: E402
import reap  # noqa: E402  — reuse run(), keep subprocess behavior in lock-step

ADMIN_PY = os.path.join(SCRIPTS_DIR, "admin.py")

LABEL = "com.fivol.feature-admin"
PLIST_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
WRAPPER_PATH = os.path.expanduser("~/.claude/bin/feature-admin")
LOG_PATH = os.path.expanduser("~/Library/Logs/feature-admin.log")

# `<...>/plugins/cache/<marketplace>/<plugin>` / `<version>` / `<relative path>`
VERSIONED_RE = re.compile(r"^(?P<family>.*/plugins/cache/[^/]+/[^/]+)/[^/]+/(?P<rel>.+)$")

STATE_RELPATH = os.path.join(".claude", "feature", "autostart.json")


# ------------------------------------------------------------------ platform
def unsupported_reason():
    """None when this platform can host the job, else a human-readable reason."""
    if sys.platform != "darwin":
        return f"only macOS/launchd is supported (this is {sys.platform})"
    if not shutil.which("launchctl"):
        return "launchctl not found"
    return None


def _uid_domain():
    return f"gui/{os.getuid()}"


# ------------------------------------------------------------- declined state
def _state_path(cfg):
    return os.path.join(cfg["_root"], STATE_RELPATH)


def read_state(cfg):
    try:
        with open(_state_path(cfg)) as f:
            return json.load(f)
    except Exception:
        return {}


def decline(cfg):
    """Remember that the user said no, so the skill stops asking."""
    path = _state_path(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    reap.atomic_write_json(path, {"declined": True})
    return path


def _clear_declined(cfg):
    path = _state_path(cfg)
    if os.path.isfile(path):
        os.remove(path)


# ------------------------------------------------------------------- probing
def job_pid():
    """PID of the loaded launchd job, 0 if loaded but not running, None if absent."""
    p = reap.run(["launchctl", "print", f"{_uid_domain()}/{LABEL}"])
    if p.returncode != 0:
        return None
    m = re.search(r"^\s*pid\s*=\s*(\d+)", p.stdout, re.M)
    return int(m.group(1)) if m else 0


def installed_root():
    """The $FEATURE_ROOT baked into the installed plist, or None."""
    try:
        with open(PLIST_PATH, "rb") as f:
            pl = plistlib.load(f)
        return (pl.get("EnvironmentVariables") or {}).get("FEATURE_ROOT")
    except Exception:
        return None


def status(cfg):
    px = config.proxy(cfg)
    port, root = px["admin_port"], cfg["_root"]
    st = {
        "label": LABEL,
        "plist": PLIST_PATH,
        "wrapper": WRAPPER_PATH,
        "log": LOG_PATH,
        "root": root,
        "port": port,
        "url": f"http://{px['admin_host']}",
        "supported": True,
        "unsupported_reason": None,
        "installed": os.path.isfile(PLIST_PATH),
        "loaded": False,
        "running": False,
        "pid": None,
        "installed_root": None,
        "root_matches": None,
        "serving": False,
        "serving_root": None,
        "declined": bool(read_state(cfg).get("declined")),
    }
    reason = unsupported_reason()
    if reason:
        # Keep the key set stable — callers (and --json consumers) read these blind.
        st.update(supported=False, unsupported_reason=reason, healthy=False, advice=reason)
        return st

    st["installed_root"] = installed_root()
    if st["installed"]:
        st["root_matches"] = os.path.realpath(st["installed_root"] or "") == os.path.realpath(root)
        pid = job_pid()                 # None = not bootstrapped, 0 = loaded but down
        st["loaded"] = pid is not None
        st["running"] = bool(pid)
        st["pid"] = pid or None
    who = admin.answering(port)
    if who:
        st["serving"] = True
        st["serving_root"] = who.get("root")
    st["healthy"] = not _problem(st)
    st["advice"] = _problem(st) or "healthy"
    return st


def _problem(st):
    """The one thing standing between this state and a working autostart, or None."""
    if not st["supported"]:
        return st["unsupported_reason"]
    if not st["installed"]:
        return "not in autostart — install with: autostart.py --install"
    if not st["root_matches"]:
        return (f"autostart points at {st['installed_root']}, not {st['root']} — "
                "re-point it with: autostart.py --install")
    if not st["loaded"]:
        return "plist present but not loaded — load it with: autostart.py --install"
    if not st["running"]:
        return f"job loaded but not running — see {st['log']}"
    if not st["serving"]:
        return f"job running but nothing answers on :{st['port']} — see {st['log']}"
    # A stranger on the port would make the job crash-loop behind a working URL.
    if st["serving_root"] and os.path.realpath(st["serving_root"]) != os.path.realpath(st["root"]):
        return (f":{st['port']} is served by {st['serving_root']}, not {st['root']} — "
                "re-point it with: autostart.py --install")
    return None


# ---------------------------------------------------------------- generation
def _interpreter():
    """A stable absolute python3 for launchd — never a venv/conda one.

    Prefers the system python3, but only when the Command Line Tools are
    actually installed: otherwise `/usr/bin/python3` is a stub that pops the
    "install developer tools" dialog the first time the job runs.
    """
    if os.path.exists("/usr/bin/python3") and reap.run(["xcode-select", "-p"]).returncode == 0:
        return "/usr/bin/python3"
    return shutil.which("python3") or sys.executable


def _launch_path():
    """PATH for the job: launchd's default has no Homebrew, where gh/caddy live."""
    dirs = []
    for tool in ("gh", "git", "caddy"):
        found = shutil.which(tool)
        if found:
            dirs.append(os.path.dirname(found))
    for d in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        dirs.append(d)
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return ":".join(out)


def wrapper_body():
    """Shell wrapper that resolves admin.py at launch time (upgrade-proof)."""
    m = VERSIONED_RE.match(ADMIN_PY)
    if m:
        resolve = (
            f'SCRIPT=$(ls -d "{m.group("family")}"/*/{m.group("rel")} 2>/dev/null'
            " | sort -V | tail -1)"
        )
        note = "# Resolves the newest installed plugin version, so upgrades don't break the job."
    else:
        resolve = f'SCRIPT="{ADMIN_PY}"'
        note = "# admin.py lives outside the plugin cache (dev checkout) — used as-is."
    return f"""#!/bin/sh
# Launch the `feature` skill admin dashboard. Generated by autostart.py.
{note}
# The workspace root comes from $FEATURE_ROOT; extra arguments reach admin.py.
set -eu

{resolve}

if [ -z "${{SCRIPT:-}}" ] || [ ! -f "$SCRIPT" ]; then
\techo "feature-admin: admin.py not found" >&2
\texit 1
fi

exec {_interpreter()} -u "$SCRIPT" "$@"
"""


def plist_dict(cfg):
    return {
        "Label": LABEL,
        "ProgramArguments": [WRAPPER_PATH],
        "EnvironmentVariables": {
            "FEATURE_ROOT": cfg["_root"],
            "PATH": _launch_path(),
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": LOG_PATH,
        "StandardErrorPath": LOG_PATH,
    }


# ------------------------------------------------------------------- install
def _write_executable(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(body)
    os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def _bootout(quiet=True):
    p = reap.run(["launchctl", "bootout", f"{_uid_domain()}/{LABEL}"])
    if not quiet and p.returncode != 0:
        print(f"  (bootout: {(p.stderr or p.stdout).strip()})")
    return p.returncode == 0


def _stop_foreign_instance(port):
    """Free the port if a hand-started dashboard holds it (the job can't bind twice)."""
    who = admin.answering(port)
    if not who:
        return False
    pid = who.get("pid") or admin.pid_on_port(port)
    if not pid or pid == job_pid():
        return False
    try:
        os.kill(int(pid), 15)
    except (ProcessLookupError, PermissionError, ValueError):
        return False
    for _ in range(20):
        if not admin.answering(port, timeout=0.4):
            return True
        time.sleep(0.25)
    return True


def install(cfg):
    reason = unsupported_reason()
    if reason:
        print(f"autostart: {reason}")
        return 2
    px = config.proxy(cfg)
    port = px["admin_port"]

    _write_executable(WRAPPER_PATH, wrapper_body())
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist_dict(cfg), f)

    _bootout()                      # replace any previous generation
    _stop_foreign_instance(port)    # a hand-started dashboard would hold the port
    p = reap.run(["launchctl", "bootstrap", _uid_domain(), PLIST_PATH])
    if p.returncode != 0:
        print(f"autostart: launchctl bootstrap failed: {(p.stderr or p.stdout).strip()}")
        return 2

    for _ in range(40):             # give the server a moment to bind
        if admin.answering(port):
            break
        time.sleep(0.25)
    _clear_declined(cfg)
    st = status(cfg)
    print(render(st))
    return 0 if st["healthy"] else 1


def uninstall(cfg):
    if unsupported_reason():
        print("autostart: nothing to remove on this platform")
        return 0
    _bootout()
    for path in (PLIST_PATH, WRAPPER_PATH):
        if os.path.isfile(path):
            os.remove(path)
    print(f"autostart: removed {LABEL} (the dashboard is no longer started at login)")
    return 0


# -------------------------------------------------------------------- render
def render(st):
    if not st["supported"]:
        return f"autostart: unsupported — {st['unsupported_reason']}"
    mark = "✓" if st["healthy"] else ("✗" if not st["installed"] else "⚠")
    lines = [f"{mark} autostart ({st['label']}) — {st['advice']}"]
    if st["installed"]:
        lines.append(f"  root: {st['installed_root']}   pid: {st['pid'] or '—'}   plist: {st['plist']}")
    if st["serving"] and not st["installed"]:
        lines.append(f"  a dashboard is running by hand on :{st['port']} (root {st['serving_root']})")
    if st["healthy"]:
        lines.append(f"  url: {st['url']}")
    elif not st["installed"] and st["declined"]:
        lines.append("  the user previously declined — don't ask again unless they bring it up")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    action = None
    for flag in ("--status", "--install", "--uninstall", "--decline"):
        if flag in args:
            args.remove(flag)
            action = flag
            break
    for a in args:
        if a in ("-h", "--help"):
            sys.exit(__doc__)
    try:
        cfg = config.load(argv=args)
    except SystemExit:
        raise
    except Exception as e:  # pragma: no cover - defensive
        print(f"autostart: internal error: {e}", file=sys.stderr)
        sys.exit(2)

    if action == "--install":
        sys.exit(install(cfg))
    if action == "--uninstall":
        sys.exit(uninstall(cfg))
    if action == "--decline":
        print(f"autostart: recorded — won't ask again ({decline(cfg)})")
        sys.exit(0)

    st = status(cfg)                # --status is the default
    print(json.dumps(st, indent=2) if as_json else render(st))
    if not st["supported"]:
        sys.exit(2)
    sys.exit(0 if st["healthy"] else 1)


if __name__ == "__main__":
    main()
