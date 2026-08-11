#!/usr/bin/env python3
"""Detached dev-server launcher for the `feature` skill (full mode).

When the agent runs as a one-shot process (e.g. `claude -p` driven by a webhook),
the turn ends and the agent exits, so a plain `cmd &` background job started
inside a Bash tool would die with it (it is a child of the tool's shell). This
launcher fully detaches the server into its own session via os.setsid(), so it is
reparented to the init/launchd process and keeps running across — and after — the
agent's turn.

Because the server becomes its own session leader, its PID == its process-group
id. That lets the reaper / finish kill the whole tree with `kill -- -<pid>`,
catching Next.js / webpack / runserver worker children too.

Usage (pass an absolute --cwd; everything after `--` is the server command):
    serve.py --cwd <workdir> --log <logfile> [--pidfile <file>] -- <cmd> [args...]

Prints the detached server's PID to stdout — capture it into the workspace state
(.feature.json ".repos.<repo>.dev_pid").

Also provides a `wait` mode that blocks until the dev-server log says it's ready
(or failed), polling the file in-process:

    serve.py wait --log <logfile> [--pattern <re>] [--fail <re>] [--timeout <sec>]

Use this instead of a bash `sleep N && tail` loop to wait for compile — the
harness blocks foreground `sleep`, and fixed sleeps are either too short (cold
cache) or waste minutes (warm). Exit 0 = ready, 1 = timeout, 2 = failure matched.
"""
import os
import re
import sys
import time


def parse_args(argv):
    cwd = None
    log = None
    pidfile = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            return cwd, log, pidfile, argv[i + 1:]
        if a == "--cwd":
            cwd = argv[i + 1]; i += 2; continue
        if a == "--log":
            log = argv[i + 1]; i += 2; continue
        if a == "--pidfile":
            pidfile = argv[i + 1]; i += 2; continue
        sys.exit(f"serve.py: unexpected arg '{a}'\n\n{__doc__}")
    sys.exit("serve.py: missing '-- <cmd>'\n\n" + __doc__)


DEFAULT_READY = (r"ready|compiled successfully|compiled client|webpack compiled|"
                 r"starting development server|local:\s+http|watching for file changes|"
                 r"ready in|event compiled")
DEFAULT_FAIL = (r"failed to compile|cannot find module|eaddrinuse|address already in use|"
                r"traceback \(most recent call last\)|modulenotfounderror|"
                r"error: listen")


def wait_main(argv):
    """Block until the dev-server log shows readiness — in-process poll, no bash sleep."""
    import argparse
    p = argparse.ArgumentParser(prog="serve.py wait")
    p.add_argument("--log", required=True)
    p.add_argument("--pattern", default=DEFAULT_READY, help="ready regex (case-insensitive)")
    p.add_argument("--fail", default=DEFAULT_FAIL, help="failure regex (case-insensitive); '' to disable")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--interval", type=float, default=1.0)
    a = p.parse_args(argv)

    ready = re.compile(a.pattern, re.I)
    fail = re.compile(a.fail, re.I) if a.fail else None
    deadline = time.monotonic() + a.timeout
    pos, buf = 0, ""
    while True:
        try:
            with open(a.log, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
        except OSError:
            chunk = ""  # log not created yet
        if chunk:
            buf += chunk
            if fail and fail.search(chunk):
                sys.stdout.write(f"FAILED: matched /{a.fail}/ in {a.log}\n")
                sys.stdout.write("\n".join(buf.splitlines()[-15:]) + "\n")
                return 2
            if ready.search(chunk):
                sys.stdout.write(f"READY: {a.log}\n")
                return 0
        if time.monotonic() >= deadline:
            sys.stdout.write(f"TIMEOUT after {a.timeout:.0f}s waiting on {a.log}\n")
            tail = "\n".join(buf.splitlines()[-15:])
            if tail.strip():
                sys.stdout.write(tail + "\n")
            return 1
        time.sleep(a.interval)


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "wait":
        sys.exit(wait_main(argv[1:]))
    cwd, log, pidfile, cmd = parse_args(argv)
    if not cmd:
        sys.exit("serve.py: empty command after '--'")
    if not log:
        sys.exit("serve.py: --log is required")

    pid = os.fork()
    if pid > 0:
        # Parent: report the detached server's PID (== its pgid) and get out of
        # the way. The child has its own session, so our exit can't touch it.
        sys.stdout.write(f"{pid}\n")
        sys.stdout.flush()
        os._exit(0)

    # Child: become a session leader, detach stdio, then exec the server.
    os.setsid()
    if cwd:
        os.chdir(cwd)
    if pidfile:
        try:
            with open(pidfile, "w") as f:
                f.write(f"{os.getpid()}\n")
        except OSError:
            pass

    devnull = os.open(os.devnull, os.O_RDONLY)
    logfd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(devnull, 0)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    for fd in (devnull, logfd):
        if fd > 2:
            os.close(fd)

    try:
        os.execvp(cmd[0], cmd)
    except OSError as exc:
        # exec failed — record why in the log so the agent can see it.
        os.write(2, f"serve.py: exec {cmd!r} failed: {exc}\n".encode())
        os._exit(127)


if __name__ == "__main__":
    main()
