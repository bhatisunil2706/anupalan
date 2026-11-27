# Security policy

## Reporting a vulnerability

Report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose
**[Report a vulnerability](https://github.com/bhatisunil2706/pramaanly/security/advisories/new)**. Include steps to
reproduce and the version or commit you tested. Please don't open a public issue or pull request for a security
problem.

- We acknowledge reports within 2 business days and give a fix timeline within 7.
- We won't take legal action against good-faith research that avoids privacy violations, data destruction
  and service disruption, and that gives us reasonable time to fix before disclosure.
- Out of scope: denial of service, social engineering, findings that need a compromised device, and reports
  from automated scanners without a demonstrated impact.

Self-hosted installations also publish this contact at `/.well-known/security.txt`.

## Supported versions

Only the latest release receives security fixes. If you run Pramaanly, update within 14 days of a security release
(7 days for anything marked critical). Watch the repository's releases to be notified.

## How Pramaanly protects your data

The full threat model and design notes are in [docs/security.md](docs/security.md). In short:

| Area | Control |
| --- | --- |
| Tenant isolation | Every company-owned table has PostgreSQL row-level security (FORCE RLS). The app connects as a role that is not a superuser and can't bypass RLS; the company is set per transaction from the server-side session. Application filters are a second layer. |
| Authentication | Argon2id password hashes; 12+ character passwords checked for strength, personal information and known breaches (k-anonymity, only a 5-character hash prefix leaves the server); account lockout; TOTP two-step verification with replay protection and single-use recovery codes; organisation-wide MFA enforcement; OIDC single sign-on (Google, Microsoft, Okta) with PKCE, state, nonce and verified domains. |
| Sessions | Opaque, server-side and revocable; 12-hour absolute and per-company idle timeouts; `__Host-` cookies (HttpOnly, Secure, SameSite); rotated after MFA; password changes and resets sign out other devices; device list. |
| Request forgery | Double-submit CSRF token on every state-changing request plus an Origin check. |
| Evidence files | AES-256-GCM with a per-company key derived via HKDF and bound to the storage key; file-type validation; optional ClamAV scanning; SHA-256 fingerprint at upload, verified on every download and in evidence packs; downloads are forced attachments under a sandbox CSP. S3 storage adds SSE-KMS. |
| Evidence review | Uploaded evidence counts only after a second person approves it (self-approval only in one-person companies, and flagged); automatic checks for reused, outdated or template documents; reproducible auditor sampling. |
| Secrets | Integration credentials are encrypted at rest; API keys are stored as hashes, scoped and shown once. |
| Audit trail | Hash-chained, per-company audit log; the app role can only append. Integrity can be verified in the product or with `python -m app.cli verify-audit`. |
| Browser hardening | Per-request nonce CSP with `strict-dynamic`, `frame-ancestors 'none'`, HSTS, nosniff, COOP/CORP, no-referrer on pages whose URL carries a token. |
| Outbound requests | Customer-supplied hosts (connectors, webhooks, data sources) are restricted to HTTPS and public addresses in production (SSRF protection). |
| AI assistant | Off by default; an owner must opt in. Only policy and control text is sent; output is parsed as data, citations are validated, and people review everything. Evidence files are sent only if the owner also turns on AI evidence checks, whose verdicts are advice and never approve evidence. |
| Supply chain | CI runs tests, ruff, bandit, pip-audit, npm audit, gitleaks and Trivy; Dependabot keeps dependencies current. |
| Operations | Containers run read-only as non-root with all capabilities dropped; TLS by Caddy; encrypted daily backups; JSON logs; Prometheus metrics including security events. |
