#!/usr/bin/env python3
"""Feature-workspace admin dashboard for the `feature` skill.

A tiny, dependency-free (stdlib only) local web app that shows every active
`feature` workspace as a card and lets you act on it: open its local URL / PR,
copy the "continue the Claude chat" command, read the agent-authored summary
(what was done / what to think about / what to test), watch the dev-server log,
and start/stop the server or run the reaper.

It reads the same source of truth the skill writes:
    worktrees/<task>/.feature.json   (per-workspace state)
    worktrees/.ports.json            (port registry)
    worktrees/<task>/summary.md      (agent-authored, rendered into the card)
    worktrees/<task>/<repo>.dev.log  (dev-server log, tailed on demand)
and enriches it live with git (ahead/behind, diffstat, last commit) and gh
(PR state + CI checks). The Claude session to resume is taken from
`.feature.json` (`session_id`, written by the skill) or, for older workspaces,
reverse-mapped from ~/.claude/projects/<slug>/*.jsonl.

Usage (from anywhere inside the workspace — it self-anchors to the root that
holds .claude/feature/config.json):
    admin.py [--port 7878] [--root DIR] [--open] [--once]

  --open   open the dashboard in the default browser after starting
  --once   print the workspaces JSON to stdout and exit (no server)

Nothing here mutates git history or merges anything: destructive steps
(finish/free-ports) are surfaced as copy-able commands, never one-click.
"""
import glob
import html
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
import config  # noqa: E402
import reap  # noqa: E402  — reuse pid_alive/run, keep behavior in lock-step

SERVE_PY = os.path.join(SCRIPTS_DIR, "serve.py")
PORTS_PY = os.path.join(SCRIPTS_DIR, "ports.py")
CADDY_PY = os.path.join(SCRIPTS_DIR, "caddyfile.py")


def serve_cmd_for(cfg, repo):
    """Dev-start command template ('{port}' placeholder) for a repo, or None.

    Comes from the repo's `dev_start` in .claude/feature/config.json. The command
    runs through serve.py (relative to the worktree cwd) so it outlives the turn.
    """
    r = config.repos(cfg).get(repo)
    return (r.get("dev_start") if r else None) or None


def base_for(cfg, repo, st):
    """Base branch to diff a worktree against: state, then config, then 'main'."""
    return (st.get("base")
            or (config.repos(cfg).get(repo) or {}).get("base_branch")
            or "main")

# Untracked worktree noise the skill/serve create — not "uncommitted work":
# dependency symlinks, build caches, dev logs, env copies, skill bookkeeping.
DIRTY_NOISE = re.compile(r"(^|/)(\.dev_pid|\.feature\.json|summary\.md|"
                         r"venv|node_modules|\.next|\.turbo|build|"
                         r".*\.dev\.log|\.env(\..*)?)/?$")

_cache = {}
_cache_lock = threading.Lock()


def cached(key, ttl, producer):
    """Tiny TTL memo so a browser auto-refresh doesn't hammer git/gh."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = producer()
    with _cache_lock:
        _cache[key] = (now, val)
    return val


# --------------------------------------------------------------- discovery
def sessions_dir(root):
    slug = os.path.realpath(root).replace("/", "-")
    return os.path.join(os.path.expanduser("~/.claude/projects"), slug)


def load_feature(task_dir):
    fj = os.path.join(task_dir, ".feature.json")
    try:
        with open(fj) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def primary_repo(cfg, repos):
    return config.primary_frontend(cfg, repos)


def git(wt, *args, timeout=8):
    return reap.run(["git", "-C", wt, *args], timeout=timeout)


def git_info(wt, base):
    """Local, fast git enrichment for one repo worktree."""
    if not os.path.isdir(wt):
        return {"exists": False}
    baseref = f"origin/{base}"
    info = {"exists": True, "ahead": None, "behind": None, "stat": "",
            "commit": None, "dirty": 0}
    r = git(wt, "rev-list", "--left-right", "--count", f"{baseref}...HEAD")
    if r.returncode == 0 and "\t" in r.stdout:
        behind, ahead = r.stdout.split()[:2]
        info["behind"], info["ahead"] = int(behind), int(ahead)
    r = git(wt, "diff", "--shortstat", f"{baseref}...HEAD")
    if r.returncode == 0:
        info["stat"] = r.stdout.strip()
    r = git(wt, "log", "-1", "--format=%h%x09%s%x09%cr")
    if r.returncode == 0 and r.stdout.strip():
        h, subj, when = (r.stdout.strip().split("\t", 2) + ["", ""])[:3]
        info["commit"] = {"hash": h, "subject": subj, "when": when}
    r = git(wt, "status", "--porcelain")
    if r.returncode == 0:
        info["dirty"] = sum(
            1 for ln in r.stdout.splitlines()
            if ln[3:] and not DIRTY_NOISE.search(ln[3:].strip()))
    return info


def gh_pr(wt, pr):
    """Networked PR state + CI rollup, cached ~45s. `pr` is a URL (or None)."""
    if not pr or not os.path.isdir(wt):
        return None

    def produce():
        r = reap.run(
            ["gh", "pr", "view", pr, "--json",
             "state,title,isDraft,mergeable,number,statusCheckRollup"],
            cwd=wt, timeout=20)
        if r.returncode != 0:
            return None
        try:
            d = json.loads(r.stdout)
        except ValueError:
            return None
        roll = d.get("statusCheckRollup") or []
        buckets = {"pass": 0, "fail": 0, "pending": 0}
        for c in roll:
            concl = (c.get("conclusion") or c.get("state") or "").upper()
            if concl in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                buckets["pass"] += 1
            elif concl in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT"):
                buckets["fail"] += 1
            else:
                buckets["pending"] += 1
        return {"state": d.get("state"), "title": d.get("title"),
                "draft": d.get("isDraft"), "mergeable": d.get("mergeable"),
                "number": d.get("number"), "checks": buckets}

    return cached(f"gh::{pr}", 45, produce)


def resume_info(task, feature, root):
    """Claude session to resume: recorded in state, else reverse-mapped."""
    sid = (feature or {}).get("session_id")
    if not sid:
        sessions = (feature or {}).get("sessions") or []
        sid = sessions[-1] if sessions else None
    if sid:
        return {"session_id": sid, "source": "recorded"}

    def produce():
        sdir = sessions_dir(root)
        if not os.path.isdir(sdir):
            return None
        # Only sessions that actually *worked inside* this worktree count — a
        # record whose cwd is under worktrees/<task>/ or whose gitBranch is the
        # task branch. Matching a bare path mention would also catch orchestrator
        # sessions that merely `git -C`'d the path (e.g. this admin's own session).
        # Branch names come from the task's own state: `branch.template` is a
        # config knob, so a hardcoded "task-<task>" would quietly stop matching
        # for any project that set one. Legacy state without a branch keeps the
        # old default.
        branches = {
            (r or {}).get("branch")
            for r in ((feature or {}).get("repos") or {}).values()
        } - {None, ""} or {f"task-{task}"}
        pat = (r'"cwd":"[^"]*worktrees/%s/|"gitBranch":"(%s)"'
               % (re.escape(task), "|".join(sorted(re.escape(b) for b in branches))))
        try:
            grep = subprocess.run(
                ['grep', '-lE', pat, *glob.glob(os.path.join(sdir, "*.jsonl"))],
                capture_output=True, text=True, timeout=25)
        except (subprocess.SubprocessError, OSError):
            return None
        best, best_ts = None, ""
        for path in grep.stdout.split():
            ts = ""
            try:
                with open(path) as f:
                    for line in f:
                        i = line.rfind('"timestamp":"')
                        if i != -1:
                            ts = line[i + 13: line.find('"', i + 13)]
                if ts > best_ts:
                    best, best_ts = path, ts
            except OSError:
                continue
        if not best:
            return None
        return os.path.splitext(os.path.basename(best))[0]

    sid = cached(f"resume::{task}", 300, produce)
    return {"session_id": sid, "source": "reverse"} if sid else None


def collect(cfg):
    """Build the full workspace list the dashboard renders."""
    root = cfg["_root"]
    wtroot = config.worktrees_root(cfg)
    suffix = config.proxy(cfg)["domain_suffix"]
    fe_key = config.frontend_sort_key(cfg)
    items = []
    for fj in sorted(glob.glob(os.path.join(wtroot, "*", ".feature.json"))):
        task_dir = os.path.dirname(fj)
        task = os.path.basename(task_dir)
        feature = load_feature(task_dir) or {}
        repos_state = feature.get("repos", {})
        prim = primary_repo(cfg, repos_state)
        repos = []
        any_live = False
        for repo in sorted(repos_state, key=fe_key):
            st = repos_state[repo] or {}
            wt = os.path.join(task_dir, repo)
            pid = st.get("dev_pid")
            alive = reap.pid_alive(pid)
            any_live = any_live or alive
            pr = st.get("pr")
            repos.append({
                "repo": repo, "branch": st.get("branch"), "base": st.get("base"),
                "port": st.get("port"), "host": st.get("host"),
                "url": st.get("url"), "pr": pr, "dev_pid": pid, "alive": alive,
                "note": st.get("note"), "is_primary": repo == prim,
                "serveable": bool(serve_cmd_for(cfg, repo)) and bool(st.get("port")),
                "git": git_info(wt, base_for(cfg, repo, st)),
                "pr_info": gh_pr(wt, pr),
            })
        items.append({
            "task": task, "mode": feature.get("mode", "full"),
            "mtime": os.path.getmtime(fj),
            "pretty_url": f"http://{task}.{suffix}" if prim else None,
            "repos": repos, "any_live": any_live,
            "has_summary": os.path.isfile(os.path.join(task_dir, "summary.md")),
            "resume": resume_info(task, feature, root),
        })
    items.sort(key=lambda x: (-x["any_live"], -x["mtime"]))
    return items


# --------------------------------------------------------------- summary md
_MD_INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)"),
     r'<a href="\2" target="_blank" rel="noopener">\1</a>'),
    (re.compile(r"(?<!\")(https?://[^\s<]+)"),
     r'<a href="\1" target="_blank" rel="noopener">\1</a>'),
]


def md_inline(text):
    out = html.escape(text)
    for pat, rep in _MD_INLINE:
        out = pat.sub(rep, out)
    return out


def render_markdown(md):
    """Minimal md→HTML — enough for the agent's summary template. Turns
    `- [ ]` / `- [x]` into real (persisted) checkboxes."""
    lines = md.splitlines()
    out, in_ul = [], False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_ul()
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_ul()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{md_inline(m.group(2))}</h{lvl}>")
            continue
        m = re.match(r"^\s*[-*]\s+\[([ xX])\]\s+(.*)$", line)
        if m:
            if not in_ul:
                out.append('<ul class="md">'); in_ul = True
            checked = "checked" if m.group(1).lower() == "x" else ""
            out.append(
                f'<li class="task"><label><input type="checkbox" {checked}>'
                f"<span>{md_inline(m.group(2))}</span></label></li>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if not in_ul:
                out.append('<ul class="md">'); in_ul = True
            out.append(f"<li>{md_inline(m.group(1))}</li>")
            continue
        m = re.match(r"^\s*_(.+)_\s*$", line)
        if m:
            close_ul()
            out.append(f'<p class="meta">{md_inline(m.group(1))}</p>')
            continue
        close_ul()
        out.append(f"<p>{md_inline(line)}</p>")
    close_ul()
    return "\n".join(out)


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def tail(path, n=40):
    try:
        with open(path, "rb") as f:
            data = f.read()[-64000:]
        text = _ANSI.sub("", data.decode("utf-8", "replace"))
        return [ln for ln in text.splitlines()][-n:]
    except OSError:
        return []


def last_agent_message(root, task, feature):
    """The agent's last *text* reply in the resumable chat — what it said when it
    stopped (the final tool_use-only record is skipped). Cached by session mtime."""
    info = resume_info(task, feature, root)
    sid = info and info.get("session_id")
    if not sid:
        return None
    path = os.path.join(sessions_dir(root), sid + ".jsonl")
    if not os.path.isfile(path):
        return None

    def produce():
        text, when = None, None
        try:
            with open(path) as f:
                for line in f:
                    if '"assistant"' not in line:   # fast skip of user/meta lines
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    content = (d.get("message") or {}).get("content")
                    if not isinstance(content, list):
                        continue
                    parts = [b.get("text") for b in content
                             if isinstance(b, dict) and b.get("type") == "text"
                             and b.get("text")]
                    if parts:                       # keep the latest text-bearing turn
                        text = "\n\n".join(parts)
                        when = d.get("timestamp")
        except OSError:
            return None
        if not text:
            return None
        return {"text": text[-9000:], "when": when, "source": info.get("source")}

    return cached(f"lastmsg::{path}::{int(os.path.getmtime(path))}", 30, produce)


# --------------------------------------------------------------- actions
def start_server(cfg, task, repo):
    root = cfg["_root"]
    wtroot = config.worktrees_root(cfg)
    feature = load_feature(os.path.join(wtroot, task))
    if not feature:
        return {"ok": False, "error": "no .feature.json"}
    st = (feature.get("repos") or {}).get(repo) or {}
    port = st.get("port")
    tpl = serve_cmd_for(cfg, repo)
    if not tpl or not port:
        return {"ok": False, "error": f"{repo} is not serveable"}
    wt = os.path.join(wtroot, task, repo)
    if reap.pid_alive(st.get("dev_pid")):
        return {"ok": True, "already": True, "pid": st.get("dev_pid")}
    cmd = shlex.split(tpl.format(port=port))
    log = os.path.join(wt, f"{repo}.dev.log")
    r = reap.run([sys.executable, SERVE_PY, "--cwd", wt, "--log", log, "--", *cmd], timeout=20)
    if r.returncode != 0:
        return {"ok": False, "error": r.stdout or r.stderr or "serve.py failed"}
    pid = int((r.stdout or "0").strip() or 0)
    st["dev_pid"] = pid
    reap.atomic_write_json(os.path.join(wtroot, task, ".feature.json"), feature)
    reap.run([sys.executable, CADDY_PY, "--root", root, "--reload"], timeout=20)
    return {"ok": True, "pid": pid}


def stop_server(cfg, task, repo):
    wtroot = config.worktrees_root(cfg)
    feature = load_feature(os.path.join(wtroot, task))
    if not feature:
        return {"ok": False, "error": "no .feature.json"}
    st = (feature.get("repos") or {}).get(repo) or {}
    pid = st.get("dev_pid")
    reap.kill_group(pid, dry=False)
    st["dev_pid"] = None
    reap.atomic_write_json(os.path.join(wtroot, task, ".feature.json"), feature)
    return {"ok": True}


def run_reap(cfg):
    r = reap.run([sys.executable, os.path.join(SCRIPTS_DIR, "reap.py"),
                  "--root", cfg["_root"], "--verbose"], timeout=90)
    return {"ok": r.returncode == 0, "out": (r.stdout or "") + (r.stderr or "")}


# --------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    cfg = None
    server_version = "FeatureAdmin/1.0"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        wtroot = config.worktrees_root(self.cfg)
        if u.path == "/":
            return self._send(200, PAGE, "text/html")
        if u.path == "/api/workspaces":
            return self._send(200, {"root": self.cfg["_root"],
                                    "suffix": config.proxy(self.cfg)["domain_suffix"],
                                    "items": collect(self.cfg)})
        if u.path == "/api/summary":
            task = (q.get("task") or [""])[0]
            p = os.path.join(wtroot, task, "summary.md")
            if not os.path.isfile(p):
                return self._send(200, {"ok": False})
            with open(p) as f:
                md = f.read()
            return self._send(200, {"ok": True, "html": render_markdown(md),
                                    "raw": md})
        if u.path == "/api/last_message":
            task = (q.get("task") or [""])[0]
            feature = load_feature(os.path.join(wtroot, task))
            m = last_agent_message(self.cfg["_root"], task, feature)
            if not m:
                return self._send(200, {"ok": False})
            return self._send(200, {"ok": True, "html": render_markdown(m["text"]),
                                    "when": m["when"], "source": m["source"]})
        if u.path == "/api/log":
            task = (q.get("task") or [""])[0]
            repo = (q.get("repo") or [""])[0]
            n = int((q.get("n") or ["40"])[0])
            p = os.path.join(wtroot, task, repo, f"{repo}.dev.log")
            return self._send(200, {"ok": os.path.isfile(p), "lines": tail(p, n)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            ln = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(ln) or "{}") if ln else {}
        except (ValueError, OSError):
            payload = {}
        task, repo = payload.get("task"), payload.get("repo")
        if u.path == "/api/server/start":
            return self._send(200, start_server(self.cfg, task, repo))
        if u.path == "/api/server/stop":
            return self._send(200, stop_server(self.cfg, task, repo))
        if u.path == "/api/reap":
            return self._send(200, run_reap(self.cfg))
        return self._send(404, {"error": "not found"})


def caddy_serves_admin(px):
    """True iff Caddy is up AND already serving the admin host — i.e. the pretty
    http://<admin_host> URL resolves, so we can drop the :port fallback as noise.

    Checks Caddy's local admin API (:2019, the default proxy-setup relies on) and
    confirms our admin host is in the running config. Any failure ⇒ treat as down.
    """
    host = px["admin_host"]
    try:
        with urllib.request.urlopen("http://127.0.0.1:2019/config/", timeout=0.6) as r:
            return host in r.read().decode("utf-8", "replace")
    except Exception:
        return False


def main():
    args = sys.argv[1:]
    cfg = config.load(argv=args)   # consumes --root from args
    px = config.proxy(cfg)
    port, do_open, once = px["admin_port"], False, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--port":
            port = int(args[i + 1]); i += 2; continue
        if a == "--open":
            do_open = True; i += 1; continue
        if a == "--once":
            once = True; i += 1; continue
        if a in ("-h", "--help"):
            sys.exit(__doc__)
        sys.exit(f"admin.py: unknown arg '{a}'\n\n{__doc__}")

    if once:
        print(json.dumps(collect(cfg), indent=2))
        return
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    local = f"http://127.0.0.1:{port}/"
    # Advertise the pretty URL only when it actually resolves: Caddy up AND we bound
    # the port Caddy proxies the admin host to (a --port override wouldn't match).
    if port == px["admin_port"] and caddy_serves_admin(px):
        url = f"http://{px['admin_host']}"
    else:
        url = local
    print(f"feature admin → {url}")
    print(f"root: {cfg['_root']}   Ctrl-C to stop")
    if do_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


# --------------------------------------------------------------- frontend
PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>feature workspaces</title>
<style>
:root{
  --bg:#0c0e13; --panel:#13161d; --panel2:#171b24; --line:#262c39;
  --txt:#e7ecf3; --dim:#8b95a7; --accent:#6ea8fe; --accent2:#9d7bff;
  --ok:#3fb950; --warn:#d29922; --bad:#f85149; --chip:#1d2230;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--txt);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;
  display:flex;flex-direction:column;height:100vh;overflow:hidden}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.muted{color:var(--dim)}
header{flex:none;background:rgba(12,14,19,.9);border-bottom:1px solid var(--line);
  padding:11px 18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header h1{font-size:15px;margin:0;font-weight:650;letter-spacing:.2px}
header h1 .dot{color:var(--accent2)}
.stats{display:flex;gap:14px;color:var(--dim);font-size:12.5px}
.stats b{color:var(--txt);font-weight:600}
.spacer{flex:1}
.btn{background:var(--chip);border:1px solid var(--line);color:var(--txt);
  padding:6px 11px;border-radius:8px;cursor:pointer;font-size:12.5px;
  display:inline-flex;align-items:center;gap:6px;transition:.12s}
.btn:hover{border-color:#3a445a;background:#1b2130}
.btn.on{border-color:var(--accent);color:var(--accent)}
.btn.ghost{background:transparent}
.btn.go{border-color:#264b2c;color:var(--ok)}
.btn.stop{border-color:#5a2530;color:var(--bad)}
.btn.mini{font-size:12px;padding:5px 9px}
.filters{display:flex;gap:6px}

/* ---- master / detail layout ---- */
.layout{flex:1;display:flex;min-height:0}
.list{width:340px;flex:none;border-right:1px solid var(--line);overflow-y:auto;
  background:#0e1117}
.detail{flex:1;overflow-y:auto;padding:22px 26px}
.list::-webkit-scrollbar,.detail::-webkit-scrollbar{width:10px}
.list::-webkit-scrollbar-thumb,.detail::-webkit-scrollbar-thumb{
  background:#222937;border-radius:6px;border:2px solid transparent;background-clip:content-box}

/* ---- left list card (compact, equal height) ---- */
.lcard{padding:12px 14px;border-bottom:1px solid var(--line);cursor:pointer;
  display:flex;flex-direction:column;gap:7px}
.lcard:hover{background:#141821}
.lcard.sel{background:#172033;box-shadow:inset 3px 0 0 var(--accent)}
.lcard .l1{display:flex;align-items:center;gap:8px}
.lcard .pdot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--dim)}
.lcard .pdot.live{background:var(--ok);box-shadow:0 0 0 3px rgba(63,185,80,.16)}
.lcard .nm{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;letter-spacing:.2px}
.lcard .age{color:var(--dim);font-size:11px;flex:none}
.lcard .l2{display:flex;gap:5px;align-items:center;overflow:hidden;height:20px}
.bdg{font-size:10.5px;border-radius:5px;padding:1px 6px;white-space:nowrap;flex:none;
  border:1px solid var(--line);background:var(--chip);color:var(--dim)}
.bdg.live{color:#7fd1a0;border-color:#264b2c}
.bdg.open{color:var(--ok)}
.bdg.merged{color:#b69bff;background:rgba(157,123,255,.12);border-color:transparent}
.bdg.dirty{color:var(--warn)}
.bdg.mode{color:var(--dim)}

/* ---- right detail ---- */
.dhead{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:4px}
.dhead .dtitle{font-size:20px;font-weight:680;letter-spacing:.2px}
.dhead .age{color:var(--dim);font-size:12px}
.mchip{font-size:11px;border-radius:6px;padding:3px 9px;font-weight:600;
  background:rgba(157,123,255,.14);color:#b69bff}
.dsub{color:var(--dim);font-size:12.5px;margin:0 0 18px}
.resume{display:flex;gap:8px;align-items:center;margin:2px 0 4px;max-width:720px}
.resume code{flex:1;background:#0e1117;border:1px solid var(--line);border-radius:8px;
  padding:7px 10px;font-size:12px;color:#b6c2d6;overflow:auto;white-space:nowrap}
.resume .src{font-size:10px;color:var(--dim)}
.hint{color:var(--dim);font-size:11.5px;margin:0 0 20px}
.sec{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--dim);
  margin:22px 0 10px;font-weight:650}
.repo{background:linear-gradient(180deg,var(--panel),var(--panel2));
  border:1px solid var(--line);border-radius:12px;padding:13px 15px;margin-bottom:11px;
  display:flex;flex-direction:column;gap:9px;max-width:840px}
.repo.live{border-color:#274b34}
.repo .r1{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.rname{font-weight:650;font-size:14.5px}
.rname .br{color:var(--dim);font-weight:400;font-size:12px}
.chip{font-size:11px;border:1px solid var(--line);background:var(--chip);
  border-radius:6px;padding:1px 7px;color:var(--dim);display:inline-flex;gap:5px;align-items:center}
.chip.ahead{color:#7fd1a0}.chip.dirty{color:var(--warn)}
.pr{font-size:11px;border-radius:6px;padding:2px 8px;font-weight:600}
.pr.OPEN{background:rgba(63,185,80,.14);color:var(--ok)}
.pr.MERGED{background:rgba(157,123,255,.16);color:#b69bff}
.pr.CLOSED{background:rgba(248,81,73,.14);color:var(--bad)}
.pr.DRAFT{background:#21262d;color:var(--dim)}
.ck{font-size:11px}.ck .p{color:var(--ok)}.ck .f{color:var(--bad)}.ck .w{color:var(--warn)}
.commit{color:var(--dim);font-size:12px}
.commit code{color:#b6c2d6;background:#0e1117;border:1px solid var(--line);padding:0 5px;border-radius:5px}
.r2{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.svc{font-size:12px;color:var(--dim)}.svc .on{color:var(--ok)}.svc .off{color:var(--dim)}
.note{font-size:12px;color:var(--dim);font-style:italic}
.logbox{background:#08090d;border:1px solid var(--line);border-radius:8px;
  margin-top:4px;padding:9px 11px;font:11.5px/1.5 ui-monospace,Menlo,monospace;
  color:#aeb7c6;max-height:300px;overflow:auto;white-space:pre-wrap}
.logbox .err{color:#ff7b72}
.sumbody{max-width:840px}
.sumbody h1{font-size:17px;margin:0 0 6px}
.sumbody h2{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--accent);margin:18px 0 6px}
.sumbody h3{font-size:13px;margin:12px 0 4px}
.sumbody p{margin:5px 0;color:#cdd6e4}
.sumbody p.meta{color:var(--dim);font-size:11.5px}
.sumbody ul{margin:5px 0;padding-left:20px}.sumbody ul li{margin:2px 0;color:#cdd6e4}
.sumbody ul.md li.task{list-style:none;margin-left:-20px}
.sumbody li.task label{display:flex;gap:8px;align-items:flex-start;cursor:pointer}
.sumbody li.task input{margin-top:3px}
.sumbody code{background:#0e1117;border:1px solid var(--line);padding:0 5px;border-radius:5px}
.lastmsg{max-width:840px;margin-bottom:18px}
.lastmsg .lmcap{color:var(--dim);font-size:11px;margin-bottom:6px}
.lastmsg .lmbody{background:linear-gradient(180deg,var(--panel),var(--panel2));
  border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  max-height:440px;overflow:auto}
.empty{color:var(--dim);padding:60px;text-align:center}
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);
  background:#1b2130;border:1px solid var(--line);padding:9px 16px;border-radius:10px;
  opacity:0;transition:.2s;pointer-events:none;font-size:12.5px;z-index:9}
.toast.show{opacity:1}
</style></head>
<body>
<header>
  <h1><span class="dot">&#9679;</span> feature workspaces</h1>
  <div class="stats" id="stats"></div>
  <div class="spacer"></div>
  <div class="filters">
    <button class="btn ghost on" data-f="all">all</button>
    <button class="btn ghost" data-f="live">live</button>
    <button class="btn ghost" data-f="open">open PR</button>
  </div>
  <button class="btn" id="reap" title="prune finished/abandoned workspaces">&#8635; reap</button>
  <button class="btn ghost" id="refresh" title="refresh now">&#8631;</button>
</header>
<div class="layout">
  <aside class="list" id="list"></aside>
  <main class="detail" id="detail"></main>
</div>
<div class="toast" id="toast"></div>
<script>
const $=s=>document.querySelector(s);
let FILTER="all", DATA={items:[]}, SELECTED=localStorage.getItem("fsel")||null, LASTJSON="", SUFFIX="localhost";
const SUM={};                       // task -> rendered summary html (cache, no flicker)
const LMSG={};                      // task -> rendered last-agent-message html
const EXPAND={log:new Set()};       // open detail logs: "task::repo"
const esc=s=>(s==null?"":String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function toast(m){const t=$("#toast");t.textContent=m;t.classList.add("show");
  clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove("show"),1800);}
async function api(p,opt){const r=await fetch(p,opt);return r.json();}
function copy(txt){navigator.clipboard.writeText(txt).then(()=>toast("copied"));}
function ago(mtime){const s=Date.now()/1000-mtime;
  if(s<90)return"just now";if(s<5400)return Math.round(s/60)+"m ago";
  if(s<172800)return Math.round(s/3600)+"h ago";return Math.round(s/86400)+"d ago";}
function checksHTML(b){if(!b)return"";const out=[];
  if(b.pass)out.push(`<span class="p">&#10003;${b.pass}</span>`);
  if(b.fail)out.push(`<span class="f">&#10007;${b.fail}</span>`);
  if(b.pending)out.push(`<span class="w">&#8226;${b.pending}</span>`);
  return out.length?`<span class="ck">${out.join(" ")}</span>`:"";}
function statSummary(g){if(!g||!g.stat)return"";
  return g.stat.replace(/ files? changed,?/,"f").replace(/insertions?\(\+\),?/,"+")
    .replace(/deletions?\(-\)/,"−").replace(/\s+/g," ").trim();}

function filtered(){let it=DATA.items||[];
  if(FILTER==="live")it=it.filter(w=>w.any_live);
  if(FILTER==="open")it=it.filter(w=>w.repos.some(r=>r.pr_info&&r.pr_info.state==="OPEN"));
  return it;}

/* ---------- left list ---------- */
function listCardHTML(w){
  const live=w.any_live?"live":"";
  const liveN=w.repos.filter(r=>r.alive).length;
  const withPR=w.repos.filter(r=>r.pr);
  const merged=withPR.length>0&&withPR.every(r=>r.pr_info&&(r.pr_info.state==="MERGED"||r.pr_info.state==="CLOSED"));
  const openN=w.repos.filter(r=>r.pr_info&&r.pr_info.state==="OPEN").length;
  const dirtyN=w.repos.reduce((a,r)=>a+((r.git&&r.git.dirty)||0),0);
  const bdg=[];
  if(liveN)bdg.push(`<span class="bdg live">&#9679; ${liveN} live</span>`);
  if(merged)bdg.push(`<span class="bdg merged">merged</span>`);
  else if(openN)bdg.push(`<span class="bdg open">${openN} open PR</span>`);
  bdg.push(`<span class="bdg">${w.repos.length} repo${w.repos.length>1?"s":""}</span>`);
  if(dirtyN)bdg.push(`<span class="bdg dirty">&#177;${dirtyN}</span>`);
  return `<div class="lcard ${w.task===SELECTED?"sel":""}" data-task="${esc(w.task)}">
    <div class="l1"><span class="pdot ${live}"></span>
      <span class="nm">${esc(w.task)}</span>
      <span class="age">${ago(w.mtime)}</span></div>
    <div class="l2">${bdg.join("")}</div>
  </div>`;
}
function renderList(){
  const it=filtered();
  const liveN=(DATA.items||[]).filter(w=>w.any_live).length;
  const prN=(DATA.items||[]).reduce((a,w)=>a+w.repos.filter(r=>r.pr).length,0);
  $("#stats").innerHTML=`<span><b>${(DATA.items||[]).length}</b> workspaces</span>
    <span><b>${liveN}</b> live</span><span><b>${prN}</b> PRs</span>`;
  $("#list").innerHTML=it.length?it.map(listCardHTML).join("")
    :`<div class="empty">no ${FILTER==="all"?"":FILTER+" "}workspaces</div>`;
  [...document.querySelectorAll(".lcard")].forEach(c=>c.onclick=()=>select(c.dataset.task));
}

/* ---------- right detail ---------- */
function repoHTML(t,r){
  const g=r.git||{};
  const ahead=(g.ahead>0)?`<span class="chip ahead">&#8593;${g.ahead}</span>`:"";
  const behind=(g.behind>0)?`<span class="chip">&#8595;${g.behind}</span>`:"";
  const dirty=(g.dirty>0)?`<span class="chip dirty">&#177;${g.dirty} uncommitted</span>`:"";
  const stat=statSummary(g)?`<span class="chip">${esc(statSummary(g))}</span>`:"";
  const pi=r.pr_info;
  let prChip="";
  if(r.pr){const state=pi?(pi.draft?"DRAFT":pi.state):"";
    prChip=`<a class="pr ${state}" href="${esc(r.pr)}" target="_blank">PR${pi&&pi.number?" #"+pi.number:""} ${state||"…"}</a> ${checksHTML(pi&&pi.checks)}`;}
  const commit=g.commit?`<div class="commit"><code>${esc(g.commit.hash)}</code> ${esc(g.commit.subject)} <span class="muted">&middot; ${esc(g.commit.when)}</span></div>`:"";
  let svc="";
  if(r.serveable){
    svc=`<span class="svc">server <span class="${r.alive?"on":"off"}">${r.alive?"&#9679; live :"+r.port:"&#9675; stopped"}</span></span>`;
    svc+=r.alive
      ?`<button class="btn mini stop" onclick="srv('${t}','${r.repo}','stop')">stop</button>
        <a class="btn mini" href="http://${esc(t)}.${SUFFIX}" target="_blank">open &#8599;</a>
        <button class="btn mini ghost" onclick="showlog(this,'${t}','${r.repo}')">log</button>`
      :`<button class="btn mini go" onclick="srv('${t}','${r.repo}','start')">start</button>
        <button class="btn mini ghost" onclick="showlog(this,'${t}','${r.repo}')">log</button>`;
  }else if(r.note){svc=`<span class="note">${esc(r.note)}</span>`;}
  return `<div class="repo ${r.alive?"live":""}" data-repo="${esc(r.repo)}">
    <div class="r1"><span class="rname">${esc(r.repo)} <span class="br">${esc(r.branch||"")}</span></span>
      ${ahead}${behind}${stat}${dirty}</div>
    ${r.pr?`<div class="r1">${prChip}</div>`:""}
    ${commit}
    <div class="r2">${svc}</div>
    <div class="logslot"></div>
  </div>`;
}
function detailHTML(w){
  if(!w)return `<div class="empty">select a workspace on the left</div>`;
  const withPR=w.repos.filter(r=>r.pr);
  const merged=withPR.length>0&&withPR.every(r=>r.pr_info&&(r.pr_info.state==="MERGED"||r.pr_info.state==="CLOSED"));
  const open=w.pretty_url?`<a class="btn mini" href="${esc(w.pretty_url)}" target="_blank">open &#8599; ${esc(w.task)}.${SUFFIX}</a>`:"";
  const mergedChip=merged?`<span class="mchip" title="all PRs merged/closed — reap to clean up">&#10003; merged &middot; reap</span>`:"";
  const rs=w.resume;let resume="",hint="";
  if(rs&&rs.session_id){const cmd=`claude --resume ${rs.session_id}`;
    resume=`<div class="resume"><code title="${esc(cmd)}">${esc(cmd)}</code>
      <button class="btn mini" onclick="copy('${esc(cmd)}')">copy</button>
      <span class="src" title="${rs.source==='recorded'?'session id written by the skill':'best-effort guess from session history'}">${rs.source}</span></div>`;
    hint=`<p class="hint">&#8594; continue the chat to iterate; say your finish word (e.g. &ldquo;done&rdquo;) to merge into the base branch and clean up the workspace</p>`;
  }else{resume=`<div class="resume muted" style="font-size:12px">chat session not found</div>`;}
  const repos=w.repos.map(r=>repoHTML(w.task,r)).join("");
  return `<div class="dhead"><span class="dtitle">${esc(w.task)}</span>
      <span class="bdg mode">${esc(w.mode)}</span><span class="age">${ago(w.mtime)}</span>
      ${open}${mergedChip}</div>
    <p class="dsub">worktrees/${esc(w.task)}/ &middot; ${w.repos.length} repo(s)</p>
    ${resume}${hint}
    <div class="sec">summary &middot; what's done / what to consider / what to test</div>
    <div class="sumbody" id="sumbody"><p class="muted">${w.has_summary?"loading…":"The agent hasn't written summary.md for this task yet."}</p></div>
    <div class="sec">last agent message</div>
    <div class="lastmsg" id="lastmsg"><p class="muted">loading…</p></div>
    <div class="sec">repositories</div>${repos}`;
}
function renderDetail(keepScroll){
  const d=$("#detail");const sy=keepScroll?d.scrollTop:0;
  const w=(DATA.items||[]).find(x=>x.task===SELECTED);
  d.innerHTML=detailHTML(w);d.scrollTop=sy;
  if(keepScroll)setTimeout(()=>{d.scrollTop=sy;},220);  // re-apply after async summary/log grow the page
  if(!w)return;
  if(w.has_summary)ensureSummary(w.task);
  ensureLastMsg(w.task);
  // re-open any logs that were open for this task
  EXPAND.log.forEach(k=>{const [t,repo]=k.split("::");if(t!==w.task)return;
    const slot=d.querySelector(`.repo[data-repo="${repo}"] .logslot`);if(slot)fillLog(slot,t,repo);});
}
async function ensureSummary(task){
  const slot=()=>{const s=$("#sumbody");return (SELECTED===task&&s)?s:null;};
  if(SUM[task]&&slot()){slot().innerHTML=SUM[task];bindChecks(slot(),task);}
  const j=await api("/api/summary?task="+encodeURIComponent(task));
  SUM[task]=j.ok?j.html:`<p class="muted">no summary</p>`;
  const s=slot();if(s){s.innerHTML=SUM[task];bindChecks(s,task);}
}
function agoIso(iso){if(!iso)return"";const t=Date.parse(iso);if(isNaN(t))return"";
  const s=Date.now()/1000-t/1000;
  if(s<90)return"just now";if(s<5400)return Math.round(s/60)+"m ago";
  if(s<172800)return Math.round(s/3600)+"h ago";return Math.round(s/86400)+"d ago";}
async function ensureLastMsg(task){
  const slot=()=>{const s=$("#lastmsg");return (SELECTED===task&&s)?s:null;};
  if(LMSG[task]&&slot())slot().innerHTML=LMSG[task];
  const j=await api("/api/last_message?task="+encodeURIComponent(task));
  LMSG[task]=j.ok
    ?`<div class="lmcap">${agoIso(j.when)} &middot; ${esc(j.source||"")}</div><div class="sumbody lmbody">${j.html}</div>`
    :`<p class="muted">no agent messages found</p>`;
  const s=slot();if(s)s.innerHTML=LMSG[task];
}

/* ---------- logs ---------- */
async function fillLog(slot,task,repo){
  const j=await api(`/api/log?task=${task}&repo=${repo}&n=80`);
  const lines=(j.lines||[]).map(l=>/error|exception|failed|traceback/i.test(l)
    ?`<span class="err">${esc(l)}</span>`:esc(l)).join("\n");
  slot.innerHTML=`<div class="logbox">${lines||"(empty)"}</div>`;slot.dataset.open="1";}
async function showlog(btn,task,repo){
  const slot=btn.closest(".repo").querySelector(".logslot");
  if(slot.dataset.open==="1"){EXPAND.log.delete(task+"::"+repo);slot.innerHTML="";slot.dataset.open="0";return;}
  EXPAND.log.add(task+"::"+repo);await fillLog(slot,task,repo);}

/* ---------- checkbox persistence ---------- */
function ckey(task,txt){return"fck:"+task+":"+txt.slice(0,80);}
function bindChecks(body,task){body.querySelectorAll("li.task").forEach(li=>{
  const cb=li.querySelector("input"),txt=li.textContent.trim(),k=ckey(task,txt);
  if(localStorage.getItem(k)==="1")cb.checked=true;
  cb.onchange=()=>localStorage.setItem(k,cb.checked?"1":"0");});}

/* ---------- selection + actions ---------- */
function select(t){SELECTED=t;localStorage.setItem("fsel",t);renderList();renderDetail(false);}
async function srv(task,repo,action){toast(action+"ing "+repo+"…");
  const j=await api("/api/server/"+action,{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({task,repo})});
  toast(j.ok?(j.already?"already running":action+"ed "+(j.pid?"(pid "+j.pid+")":"")):"error: "+(j.error||"?"));
  setTimeout(load,action==="start"?1500:400);}
$("#reap").onclick=async()=>{toast("reaping…");await api("/api/reap",{method:"POST"});toast("reap done");load();};
$("#refresh").onclick=()=>load();
document.querySelectorAll(".filters .btn").forEach(b=>b.onclick=()=>{
  FILTER=b.dataset.f;document.querySelectorAll(".filters .btn").forEach(x=>x.classList.toggle("on",x===b));
  ensureSelectedValid();renderList();renderDetail(false);});

function ensureSelectedValid(){const it=filtered();
  if(!it.length){SELECTED=null;return;}
  if(!it.some(w=>w.task===SELECTED))SELECTED=it[0].task;}

async function load(){try{
  const d=await api("/api/workspaces");
  SUFFIX=d.suffix||"localhost";
  const sig=JSON.stringify(d.items);
  const first=!LASTJSON;
  if(sig===LASTJSON){return;}
  LASTJSON=sig;DATA=d;ensureSelectedValid();renderList();renderDetail(!first);
}catch(e){}}
load();setInterval(load,7000);
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
