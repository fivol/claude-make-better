# Cross-cutting merge guidance (loaded by main agent in Phase 2)

After Phase 1, you (the main agent) hold one JSON object per subsystem. Your job in Phase 2 is to fold cross-cutting systems together, normalize names, and group everything into sections — before showing the user the plan list.

## Cross-cutting merge

For every pair of systems across different subsystems, check if they should be one system:

### Match signals
- **Same conceptual name** (modulo direction suffix): "Google Auth (web side)" + "Google Auth (server side)" → "Google Auth (web → server)".
- **Cross-cutting hint pointing at the partner:** subsystem A's proposal has `cross_cutting_hint: "server"` AND subsystem B (server) has a system with a closely related name → merge.
- **Shared contract:** both systems' areas reference the same `common/types/<name>.ts` or the same `docs/CONTRACTS/<name>.md` → strong signal they are cooperating.
- **Notes references:** subsystem A's notes mention "consumed by server" and subsystem B (server) has a system that fits the description.

### Match procedure
1. Build an index: subsystem → list of proposed systems with their notes and areas.
2. For each proposed system, scan other subsystems' proposals for partners using the signals above.
3. Confirm by reading the relevant `common/types/` or contract file and checking that both sides actually use it.
4. If confirmed, merge:
   - Combine `areas` (deduplicate).
   - Combine `notes` (concatenate with semicolon).
   - Pick the merged name following naming conventions: `<Concept> (<from-subsystem> → <to-subsystem>)` for client→server flows, or `<Concept> (<subsystems>)` for symmetric.
   - Pick the section that the user is more likely to expect — usually the higher-level concept (Auth, Sync) over the lower (Server Routing).

### Naming conflicts
If two scan agents proposed the same name for unrelated things (rare but possible), suffix with the subsystem: `Recent Panel (flutter)` vs `Recent Panel (admin)`.

### Section organization
- Reuse existing section names from the registry whenever a proposed system fits.
- Group systems by purpose, not by where files live. `Auth` contains all auth flows regardless of subsystem. `Sync` contains all sync mechanics regardless of subsystem.
- A section is created if you have ≥3 proposed systems that don't fit any existing section AND share a coherent theme. For 1–2 orphans, place them in the closest existing section or `Misc`.

### Output of Phase 2 (held in main agent's memory)

For internal use, structured as:

```json
{
  "proposed_systems": [
    {
      "name": "Google Auth (web → server)",
      "section": "Auth",
      "areas": ["src/client/auth/...", "src/routes/auth.ts", "..."],
      "notes": "OAuth flow; web initiates, server validates id_token.",
      "marker": "NEW" | "REBUILT",
      "preserved_from_existing": null | { "name": "<old name>", "last_review": "...", "status": "...", "blocker": "..." }
    }
  ],
  "areas_patches": [
    { "existing_system_name": "...", "new_areas": ["..."], "reason": "..." }
  ],
  "notes_appends": [
    { "existing_system_name": "...", "append": "..." }
  ]
}
```

- `marker: "NEW"` for genuinely new systems.
- `marker: "REBUILT"` for systems that exist in the current registry but are within rebuild scope and being re-derived.
- `preserved_from_existing` is set when rebuild produced a system with the same name as an existing one — the existing review fields should be carried over.

This shape feeds Phase 4 (plan mode rendering) and Phase 5 (writing).
