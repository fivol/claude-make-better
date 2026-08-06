# Angle Prior review — what reviewers already said here · light · level `max`

```bash
gh api "repos/{owner}/{repo}/pulls/comments?per_page=100" --paginate \
  -q '.[] | select(.path=="<changed file>") | "\(.path):\(.line) \(.user.login): \(.body)"' | head -100
```

Review comments left on **earlier** PRs that touched these same files. A point already made once and
now repeated in the diff is a high-value finding: it is a known team preference the change walked
back into.

**Cite the old comment's URL.**

Skip comments carrying this workspace's agent marker on the current branch — those are this change's
own review, not prior art, and picking them up makes the gate answer itself.

`gh` unavailable, not authenticated, or the repo has no PR history ⇒ return nothing and say which.
