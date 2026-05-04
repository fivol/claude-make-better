---
name: completeness
required: true
---

# Completeness (intent vs implementation)

This topic is about the **gap between what the system was meant to do and what it actually handles**. Bugs are wrong behavior in code paths that exist. Completeness is about code paths that should exist for the intent to be fully served — but don't.

## Step 0: Understand the intent

Before searching for gaps, build a mental model of what this system is supposed to do and for whom. Read in this order:

- `notes:` of the system in `SYSTEMS.md`.
- Top-of-file comments and module headers in `areas:`.
- The closest related docs in `docs/` (e.g., `docs/AGENT_MAP/<subsystem>.md`, `docs/CONTRACTS/`, `docs/PRODUCT/`).
- Recent commits and PR descriptions touching `areas:` (`git log --follow -- <path>`).

Distill: **"this system exists to do X for users who Y, under conditions Z."** Hold that sentence in mind for the next steps.

## What to look for

For each axis below, ask: *"Is there a realistic scenario in this axis where the stated intent should hold, but the code currently does nothing or does the wrong thing silently?"*

### 1. Browser / platform reality
- Popup blockers, redirect interceptors, third-party-cookie restrictions.
- Mobile WebView quirks (iOS Safari, Android Chrome, embedded WebView in Telegram or Electron).
- Browser-specific behavior that diverges from the spec assumption (Firefox forcing auth into a popup, Safari blocking storage in private mode, etc.).
- OS dialogs interrupting flows (file picker, share sheet, biometric prompts).

### 2. Network reality
- Offline / flaky network, partial loads, mid-stream disconnects.
- Very slow responses (loading states absent or premature timeout).
- Retries that aren't idempotent. Stale CDN/proxy caches. Aborted requests on navigation.

### 3. Concurrency reality
- Same user, two tabs or two devices, simultaneous edits.
- Two clicks before the first request returns.
- Session expiring mid-action; token refresh racing with another request.
- WebSocket reconnect arriving after the user already moved on.

### 4. Permission reality
- User denies the prompt; user revokes permission later in settings.
- Enterprise-managed restrictions, parental controls, restricted accounts.
- Browser quotas (storage, push, notifications) hit mid-flow.

### 5. Input reality
- Very long, very short, empty, whitespace-only, paste-with-formatting inputs.
- Unicode: RTL, combining marks, emoji, zero-width characters, scripts the UI font doesn't render.
- Locale: dates, numbers, currencies in formats the parser doesn't expect.

### 6. State reality
- Action repeated quickly (double-click, double-tap, repeated swipe).
- User leaves mid-flow and comes back hours later (state expired, draft lost).
- Force-quit, app backgrounded for hours, OS clock changed (DST, timezone change).

### 7. Lifecycle reality
- First-run experience: zero data, no preferences set yet, no cached identity.
- Returning after migration / app upgrade with old local data shape.
- Resumed-from-background: stale tokens, stale subscriptions, stale UI state.
- Low-memory recycling on mobile (Activity/Scene destroyed, then restored).

### 8. Empty / loaded boundaries
- Zero items in the list/board/tree.
- Exactly one item (often hits singular/plural and "no comparison" branches).
- The maximum count the UI was designed for; one beyond it.
- Items that are themselves empty or malformed.

### 9. Auth and access reality
- Logged-out user reaches a code path designed for logged-in users.
- Sharing a link to someone without access — what do they see?
- Account just deleted on another device, but local session still cached.
- Token expiry mid-action; refresh failure mid-action.

### 10. Failure reality
- Dependency unavailable (server down, third-party API down, disk full).
- Partial success: some items written, some failed — what does the user see and what is recoverable?

## What NOT to look for
- Logic errors in code paths the implementation already covers → `bugs`.
- Missing test cases for behavior that IS implemented → `tests`.
- Naming, style, error-handling style → `consistency`.
- Architectural layering → `architecture`.
- Performance under load → `efficiency`.

## Procedure
1. Build the intent sentence (Step 0).
2. Walk the 10 axes. For each, name 1–3 concrete scenarios that the intent implies should work.
3. Check the code: does each scenario have a corresponding path? If yes, skip (it belongs to `bugs` or `tests` if it's broken). If no, that's a completeness gap.
4. Describe each gap as a user-visible scenario, not as "missing handler for X".
5. Be conservative on severity: not every theoretical edge case deserves to ship a fix. Weight by realistic frequency × user impact.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "src/client/auth_client.ts",
  "line": 0,
  "issue": "Auth redirect assumes same-tab navigation. Firefox with strict popup blocker opens the auth provider in a popup, leaving the original tab on the login screen — the redirect callback never reaches the original tab and the user is stuck.",
  "severity": "high",
  "suggested_fix": "Detect popup-vs-tab via window.opener after callback; fall back to BroadcastChannel or postMessage so the originating tab can resume the flow."
}
```

- `severity`:
  - `"high"` — realistic scenario for a sizable user segment, completely breaks the system for them.
  - `"medium"` — plausible scenario that partially breaks the flow or leaves the user confused without a clear recovery path.
  - `"low"` — edge case affecting few users; worth noting but not urgent.
- `line: 0` is acceptable — completeness gaps are usually about code that doesn't exist rather than a specific line.
- `issue` must describe the user-visible scenario in plain language. Avoid "missing handler"-style abstractions.

Return `[]` if intent and implementation match across the axes above.
