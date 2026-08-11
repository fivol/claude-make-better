#!/usr/bin/env python3
"""PR review feedback for the `iteration` skill — collect it, answer it.

The reviewer's comments on the PR are work items, exactly like the user's chat
prompt. This script is the plumbing: one command lists what is still
unaddressed, two more post the answers back.

    pr_feedback.py list    [--pr URL] [--cwd DIR] [--json] [--all]
    pr_feedback.py reply   --thread ID  --body TEXT | --body-file FILE
    pr_feedback.py reply   --issue [--to URL] [--pr URL] [--cwd DIR] --body TEXT
    pr_feedback.py resolve --thread ID

WHY A MARKER, NOT AN AUTHOR FILTER
`gh` is authenticated as the human whose PR this is, so the agent's replies are
authored by that same account — "the last comment is mine" is true even when the
agent wrote it, and `viewerDidAuthor` can't tell them apart either. So every
reply this script posts carries a marker (an HTML comment, invisible in the
GitHub UI), and a thread counts as UNADDRESSED when it is unresolved and its
last comment does NOT carry that marker.

Non-threaded items (review bodies, general PR comments) have no thread to reply
into, so the answer is a general comment that NAMES what it answers:
`--to <url>` embeds that url in the marker, and the item counts as answered only
when some marked comment references it. An earlier design used the newest marked
comment as a blanket watermark, which silently marked *every* older item
answered — answer one of two review bodies and the other disappeared. Naming the
target under-marks instead (forget `--to` and the item resurfaces), and for a
tool whose whole job is not losing work items, that is the right way to fail.

`isOutdated` is deliberately NOT a filter: a comment goes outdated the moment a
fix touches that file, so outdated threads are usually the ones just worked on —
their line is gone, which is why the diff hunk is carried into the output.

Everything is driven by the `pr_feedback` block of the feature config (see
defaults.json); with no config at all the shipped defaults apply, so this works
standalone as well as inside a feature workspace.

Exit codes: 0 ok · 1 usage/config error · 2 gh/network failure.
"""
import argparse
import json
import os
import re
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
import config  # noqa: E402
import reap  # noqa: E402  — reuse run(): one timeout/OSError policy for all scripts

PR_URL_RE = re.compile(r"https?://[^/]+/([^/]+)/([^/]+)/pull/(\d+)")

QUERY = """
query($owner:String!,$name:String!,$number:Int!){
  repository(owner:$owner,name:$name){
    pullRequest(number:$number){
      number url state title reviewDecision
      reviewThreads(first:100){ pageInfo{hasNextPage} nodes{
        id isResolved isOutdated path line originalLine
        comments(first:50){ pageInfo{hasNextPage}
          nodes{ author{login} body createdAt url diffHunk } } } }
      reviews(first:50){ pageInfo{hasNextPage}
        nodes{ author{login} state body submittedAt url } }
      comments(first:100){ pageInfo{hasNextPage}
        nodes{ author{login} body createdAt url } }
    }
  }
}
"""

REPLY_MUTATION = """
mutation($id:ID!,$body:String!){
  addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$id, body:$body}){
    comment{ url } } }
"""

RESOLVE_MUTATION = """
mutation($id:ID!){ resolveReviewThread(input:{threadId:$id}){ thread{ isResolved } } }
"""


def die(msg, code=1):
    print(f"pr_feedback: {msg}", file=sys.stderr)
    sys.exit(code)


def gh(args, cwd=None, timeout=30):
    """Run `gh`, returning (ok, output). Never raises; errors come back as text."""
    p = reap.run(["gh", *args], cwd=cwd, timeout=timeout)
    return (p.returncode == 0), (p.stdout if p.returncode == 0 else p.stderr).strip()


def resolve_pr(url, cwd):
    """(owner, repo, number, url) for the PR — explicit URL, else the branch's."""
    if not url:
        ok, out = gh(["pr", "view", "--json", "url", "-q", ".url"], cwd=cwd)
        url = out if ok else ""
    m = PR_URL_RE.search(url or "")
    if not m:
        return None
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    return owner, repo, number, m.group(0)


def fetch(owner, repo, number, cwd):
    ok, out = gh(["api", "graphql", "-f", f"query={QUERY}", "-F", f"owner={owner}",
                  "-F", f"name={repo}", "-F", f"number={number}"], cwd=cwd)
    if not ok:
        return None, out
    try:
        return json.loads(out)["data"]["repository"]["pullRequest"], None
    except (ValueError, KeyError, TypeError) as exc:
        return None, f"unexpected gh response: {exc}"


def login(node):
    """GitHub login of a comment/review author ('' for a deleted account)."""
    return ((node or {}).get("author") or {}).get("login") or ""


def hunk_tail(text, lines=8):
    """Last few lines of a diff hunk — enough context when the line is gone."""
    rows = (text or "").splitlines()
    return "\n".join(rows[-lines:])


def stem_of(marker):
    """The marker without its closing `-->`, so `<!-- m -->` and `<!-- m to=U -->` both match."""
    return marker[:-3].rstrip() if marker.endswith("-->") else marker


def stamp(marker, to=None):
    """The marker to append to a reply, naming the item it answers when given."""
    if not to:
        return marker
    return (f"{stem_of(marker)} to={to} -->" if marker.endswith("-->")
            else f"{marker} to={to}")


def truncations(pr):
    """Connections GitHub capped — silently dropping work items would be worse."""
    hit = []
    if pr["reviewThreads"]["pageInfo"]["hasNextPage"]:
        hit.append("review threads (>100)")
    if pr["reviews"]["pageInfo"]["hasNextPage"]:
        hit.append("reviews (>50)")
    if pr["comments"]["pageInfo"]["hasNextPage"]:
        hit.append("PR comments (>100)")
    if any(t["comments"]["pageInfo"]["hasNextPage"] for t in pr["reviewThreads"]["nodes"]):
        hit.append("comments inside a thread (>50)")
    return hit


def collect(pr, pol, keep_all=False):
    """Split the PR's feedback into what still needs an answer."""
    marker = pol["marker"]
    stem = stem_of(marker)
    ref_re = re.compile(re.escape(stem) + r"\s+to=(\S+?)\s*(?:-->|$)", re.M)

    def mine(body):  # written by the agent (carries the marker, with or without `to=`)
        return stem in (body or "")

    def wanted_author(node):
        return pol["include_bots"] or not login(node).endswith("[bot]")

    threads = []
    for t in pr["reviewThreads"]["nodes"]:
        comments = t["comments"]["nodes"]
        if not comments:
            continue
        if not keep_all:
            if t["isResolved"] or mine(comments[-1]["body"]):
                continue
            if t["isOutdated"] and not pol["include_outdated"]:
                continue
            if not wanted_author(comments[0]):
                continue
        threads.append({
            "id": t["id"],
            "path": t["path"],
            "line": t["line"] if t["line"] is not None else t["originalLine"],
            "line_gone": t["line"] is None,
            "outdated": t["isOutdated"],
            "resolved": t["isResolved"],
            "url": comments[0]["url"],
            "diff_hunk": hunk_tail(comments[0].get("diffHunk")),
            "comments": [{"author": login(c), "body": c["body"],
                          "created_at": c["createdAt"], "agent": mine(c["body"])}
                         for c in comments],
        })

    # Review bodies and general comments have no thread to reply into — the
    # answer is a general comment that names its target (`--to`), so an item is
    # answered exactly when some marked comment references its url.
    generals = pr["comments"]["nodes"]
    answered = {u for c in generals if mine(c["body"])
                for u in ref_re.findall(c["body"] or "")}

    def unanswered(node):
        return keep_all or (not mine(node["body"]) and node["url"] not in answered
                            and wanted_author(node))

    issue_comments = [
        {"author": login(c), "body": c["body"],
         "created_at": c["createdAt"], "url": c["url"]}
        for c in generals if unanswered(c)
    ]
    reviews = [
        {"author": login(r), "state": r["state"], "body": r["body"],
         "submitted_at": r["submittedAt"], "url": r["url"]}
        for r in pr["reviews"]["nodes"]
        if (r["body"] or "").strip() and unanswered(r)
    ]
    return threads, reviews, issue_comments


# ------------------------------------------------------------------ rendering
def render(data):
    """Compact human/agent-readable digest of the JSON payload."""
    if not data["enabled"]:
        return "pr_feedback: disabled in config — skipping."
    if not data["pr"]:
        return "pr_feedback: no PR for this branch yet — nothing to pick up."
    c = data["counts"]
    pr = data["pr"]
    head = (f"PR #{pr['number']} ({pr['state']}) {pr['url']}\n"
            f"unaddressed: {c['threads']} thread(s) · {c['reviews']} review(s) · "
            f"{c['issue_comments']} comment(s)")
    if data.get("truncated"):
        head += ("\n!! GitHub capped " + ", ".join(data["truncated"])
                 + " — some feedback is NOT in this list; open the PR and check by hand")
    if not c["total"]:
        return head + "\n(nothing to address)"
    out = [head]
    for t in data["threads"]:
        where = f"{t['path']}:{t['line']}" if t["line"] else t["path"]
        flags = " [outdated — line moved/gone]" if t["outdated"] else ""
        out.append(f"\n--- thread {t['id']}\n{where}{flags}  {t['url']}")
        if t["diff_hunk"]:
            out.append("code:\n" + t["diff_hunk"])
        for cm in t["comments"]:
            who = "agent" if cm["agent"] else cm["author"]
            out.append(f"  [{who}] {cm['body']}")
    for r in data["reviews"]:
        out.append(f"\n--- review by {r['author']} ({r['state']})  {r['url']}\n{r['body']}")
    for ic in data["issue_comments"]:
        out.append(f"\n--- comment by {ic['author']}  {ic['url']}\n{ic['body']}")
    return "\n".join(out)


# ------------------------------------------------------------------- commands
def cmd_list(args, cfg):
    pol = config.pr_feedback(cfg)
    data = {"ok": True, "enabled": pol["enabled"], "pr": None, "policy": pol,
            "threads": [], "reviews": [], "issue_comments": [],
            "counts": {"threads": 0, "reviews": 0, "issue_comments": 0, "total": 0}}
    if not pol["enabled"]:
        return data, 0

    target = resolve_pr(args.pr, args.cwd)
    if not target:
        return data, 0
    owner, repo, number, url = target
    pr, err = fetch(owner, repo, number, args.cwd)
    if pr is None:
        data.update({"ok": False, "error": err})
        return data, 2

    threads, reviews, issue_comments = collect(pr, pol, args.all)
    data["truncated"] = truncations(pr)
    data["pr"] = {"owner": owner, "repo": repo, "number": pr["number"],
                  "url": pr["url"] or url, "state": pr["state"],
                  "title": pr["title"], "review_decision": pr["reviewDecision"]}
    data["threads"] = threads
    data["reviews"] = reviews
    data["issue_comments"] = issue_comments
    data["counts"] = {"threads": len(threads), "reviews": len(reviews),
                      "issue_comments": len(issue_comments),
                      "total": len(threads) + len(reviews) + len(issue_comments)}
    return data, 0


def body_of(args):
    if not args.body_file:
        return (args.body or "").strip()
    if args.body_file == "-":
        return sys.stdin.read().strip()
    with open(args.body_file) as f:
        return f.read().strip()


def cmd_reply(args, cfg):
    pol = config.pr_feedback(cfg)
    body = body_of(args)
    if not body:
        die("reply needs --body or --body-file")
    if args.to and not args.issue:
        die("--to only applies to --issue (a thread reply already names its target)")
    if stem_of(pol["marker"]) not in body:
        body = f"{body}\n\n{stamp(pol['marker'], args.to)}"

    if args.issue:
        target = resolve_pr(args.pr, args.cwd)
        if not target:
            die("reply --issue needs a PR (--pr URL, or run inside the worktree)")
        ok, out = gh(["pr", "comment", target[3], "--body", body], cwd=args.cwd)
    else:
        if not args.thread:
            die("reply needs --thread ID (or --issue for a general PR comment)")
        ok, out = gh(["api", "graphql", "-f", f"query={REPLY_MUTATION}",
                      "-f", f"id={args.thread}", "-f", f"body={body}"], cwd=args.cwd)
    if not ok:
        return {"ok": False, "error": out}, 2
    return {"ok": True, "result": out}, 0


def cmd_resolve(args, cfg):
    if not args.thread:
        die("resolve needs --thread ID")
    ok, out = gh(["api", "graphql", "-f", f"query={RESOLVE_MUTATION}",
                  "-f", f"id={args.thread}"], cwd=args.cwd)
    if not ok:
        return {"ok": False, "error": out}, 2
    return {"ok": True, "result": out}, 0


def main():
    ap = argparse.ArgumentParser(prog="pr_feedback.py", description=__doc__)
    ap.add_argument("command", choices=["list", "reply", "resolve"])
    ap.add_argument("--root", help="workspace root (default: resolved from cwd)")
    ap.add_argument("--pr", help="PR URL (default: the current branch's PR)")
    ap.add_argument("--cwd", help="repo/worktree dir gh runs in (default: cwd)")
    ap.add_argument("--thread", help="review-thread node id (reply/resolve)")
    ap.add_argument("--issue", action="store_true",
                    help="reply as a general PR comment instead of in a thread")
    ap.add_argument("--to", metavar="URL",
                    help="with --issue: url of the review body / comment this answers "
                         "(that item counts as answered only once some reply names it)")
    ap.add_argument("--body", help="reply text")
    ap.add_argument("--body-file", help="read the reply text from a file ('-' = stdin)")
    ap.add_argument("--all", action="store_true",
                    help="list everything, including what's already answered")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    if args.cwd and not os.path.isdir(args.cwd):
        die(f"--cwd {args.cwd} is not a directory")
    cfg = config.load(root=os.path.abspath(args.root) if args.root else None)

    handler = {"list": cmd_list, "reply": cmd_reply, "resolve": cmd_resolve}[args.command]
    data, code = handler(args, cfg)

    if args.json or args.command != "list":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(render(data))
        if not data.get("ok"):
            print(f"pr_feedback: {data.get('error')}", file=sys.stderr)
    sys.exit(code)


if __name__ == "__main__":
    main()
