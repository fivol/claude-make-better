---
name: security
required: false
---

# Security

## When to apply
Dispatch this topic when the system involves any of:
- handling secrets, tokens, or passwords
- any authentication or authorization flow
- external inputs (HTTP, WebSocket, webhooks, file upload, deep links)
- user PII (email, phone, payments)
- payments, billing, or licensing
- cross-service communication across a trust boundary

If none of the above apply, skip the topic and report `skipped` with a one-line reason to the review agent.

## What to look for
- Injection vectors: SQL, command, template, log injection.
- Secrets in logs, error responses, or client-visible payloads.
- Missing authn/authz checks on protected paths.
- Weak cryptography (MD5/SHA1 for security purposes, custom crypto, predictable nonces) or improper random sources (`Math.random` for secrets).
- Trust-boundary crossings without validation: untrusted input into trusted code paths.
- Sensitive data persisted unencrypted or logged.
- Open redirects, missing CSRF protection on state-changing endpoints, missing rate limits on auth endpoints.

## What NOT to look for
- Generic bugs unrelated to security → `bugs`.
- Performance of crypto code → `efficiency`.

## Output format
Return a JSON array. Each entry:

```json
{
  "file": "src/routes/auth.ts",
  "line": 88,
  "issue": "session token included in 500 response body",
  "severity": "critical",
  "suggested_fix": "do not return token in error responses; log redacted"
}
```

- `severity`: `"critical"` (exploitable, low-effort, high-impact) | `"high"` | `"medium"` | `"low"`.

Return `[]` if applicable but nothing found. Return `skipped` with reason if not applicable.
