---
description: Preflight-check the Feature toolchain (git, gh, config, repos, Caddy) and fix/instruct
argument-hint: "[--root DIR] [--mode full|lite]"
---

Run the Feature preflight doctor and act on it. It's read-only — it verifies everything the
`feature` skill needs before building:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/feature/scripts/doctor.py" $ARGUMENTS
```

Then handle the results, splitting by the owner tag the doctor prints:

- **`[agent]`** — do it yourself now (create `.claude/feature/config.json`, `brew install gh` if
  missing — say you're doing it), then re-run the doctor.
- **`[user]`** — you can't do these; relay the exact command verbatim (`gh auth login`,
  `proxy-setup.sh` for pretty URLs, cloning a missing repo, installing a repo's dev deps).

Exit `1` means a `[user]` action blocks building — surface those lines clearly. Warnings
(dev-server deps, Caddy) are non-blocking: note them and how to enable them. Run from the workspace
root (the script self-anchors), or pass `--root DIR`.
