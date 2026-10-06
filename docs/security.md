# Security design and threat model

This document is for security reviewers, customers' security teams and auditors. It describes what we protect,
from whom, and how. Keep it current with every security-relevant change.

## What we protect

1. **Customer compliance data**: policies, risks, incidents, personal data inventories, vendor assessments.
2. **Evidence files**: screenshots, exports and reports that can contain personal or confidential data.
3. **Integration credentials**: tokens for identity providers, cloud accounts, HR systems.
4. **Consent records**: legally significant proof of what a data principal agreed to.
5. **The audit trail**: proof of who did what, used in audits and disputes.

## Who we defend against

| Actor | Example goals |
| --- | --- |
| A user of company A | Read or change company B's data |
| An external attacker | Take over accounts, steal evidence or credentials |
| A malicious vendor answering a questionnaire | Upload malware, reach other data through the link |
| A compromised integration or IdP response | Inject data, reach internal networks (SSRF) |
| Prompt injection in uploaded questionnaires or policies | Make the AI leak data or produce harmful output |
| An insider with database access | Silently alter the audit trail |

## Tenant isolation

- Two layers. Every query filters by organisation in application code, **and** PostgreSQL row-level security
  enforces it independently.
- The app connects as `app_runtime` (NOSUPERUSER, NOBYPASSRLS). Tables use `FORCE ROW LEVEL SECURITY`.
- The organisation and user are set as transaction-local settings (`app.org_id`, `app.user_id`) from the
  server-side session at the start of each transaction.
- Startup refuses to run in production if the role can bypass RLS.
- A handful of flows must look across tenants before the tenant is known (login, SSO domain lookup, public
  questionnaire and privacy-portal links, API key lookup). These set `app.rls_bypass` for one lookup and drop it
  immediately. The bypass setting is a guard against missing filters, not against SQL injection; all SQL is
  parameterised.
- Shared reference content (frameworks, controls catalogue, templates, courses) is read-only for the runtime role.
- `audit_logs` and `consent_events` are append-only for the runtime role (UPDATE and DELETE revoked).

Tested by `tests/test_security.py::test_rls_blocks_cross_tenant_reads_and_writes` and tenant-isolation tests in
each feature suite.

## Authentication and sessions

- Passwords: Argon2id, minimum 12 characters, zxcvbn score of at least 3, rejected if they contain the user's name,
  email or company, and rejected if found in the Have I Been Pwned corpus (k-anonymity range API; fails open if
  unreachable). Constant-time verification with a dummy hash for unknown users.
- Lockout after 10 failed attempts per account per hour (shared in Redis), plus per-IP limits. Responses don't
  reveal whether an account exists.
- TOTP (RFC 6238) with ±1 step drift and replay protection (last used time step stored). 10 single-use recovery
  codes stored as keyed hashes. MFA attempts are capped per challenge session.
- Organisations can require MFA; users without it can reach only account-security screens.
- SSO: OIDC authorisation code flow with PKCE, state and nonce; ID tokens verified (signature via JWKS, issuer,
  audience, expiry, nonce, `email_verified`). Accounts are matched only for **verified** domains (DNS TXT record).
  SSO can be enforced; owners keep password access as a break-glass path.
- Sessions are random 256-bit tokens; only their SHA-256 is stored. 12-hour absolute lifetime, configurable idle
  timeout, revocable individually or all at once. Cookies use the `__Host-` prefix in production.
- Email verification is required before inviting others. Password reset tokens are single-use, expire in 30
  minutes and revoke all sessions.
- Auditor access is time-limited at the membership level.

## Request integrity

- CSRF: double-submit token (`__Host-csrf` cookie echoed in `X-CSRF-Token`) on all state-changing requests with a
  session, plus an Origin/Referer check against the configured origins.
- JSON bodies are capped at 2 MB; uploads at 25 MB.
- Global per-IP rate limit, plus endpoint-specific limits for sign-in, SSO, password reset, public portals and
  questionnaire links.
- **Client IP**: in production Caddy replaces any client-supplied `X-Forwarded-For`, and the backend is reachable
  only from the web container, so uvicorn trusts forwarded headers. Without a front proxy (local development) the
  forwarded IP can be spoofed; don't expose the web container directly in production.

## Evidence and file handling

- Files are encrypted with AES-256-GCM using a per-organisation key derived with HKDF-SHA256 from the master
  encryption key; the storage key is the associated data, so a ciphertext can't be moved between organisations or
  paths. Keys are bound to the organisation prefix and checked on every read.
- Uploads are checked against an allow-list of extensions and their magic bytes; executables are rejected.
  ClamAV scanning is used when `CLAMAV_ADDRESS` is set.
- Downloads are served as attachments with `Content-Security-Policy: sandbox`, `nosniff` and `no-store`, and are
  recorded in the audit log.
- Evidence packs include a manifest of SHA-256 hashes; the manifest hash is written to the audit log.

## Audit log

- Each entry stores `prev_hash` and `hash = SHA-256(prev_hash || canonical JSON of the entry)`, chained per
  organisation with a locked chain head so concurrent writers can't fork it.
- The runtime role can't update or delete entries. Anyone with owner database access could still rewrite the whole
  chain; to detect that, export the latest hash to an external system (for example in the monthly evidence pack).

## Integrations and outbound requests

- Credentials are encrypted at rest (Fernet) and never returned by the API.
- Customer-supplied URLs must be HTTPS. In production, hosts resolving to private, loopback, link-local or
  reserved addresses are refused. Connectors that follow pagination links refuse links to other hosts.
- Personal-data scanning of private networks is done by the self-hosted agent, which sends only categories, counts
  and masked examples. The server masks examples again regardless of what the agent sends.

## AI assistant

- Off by default; only the owner can turn it on, after acknowledging what is shared.
- Only the organisation's own policy text, control descriptions and implementation notes, framework requirements
  and the questions the user uploads are sent. Evidence files, people data, consent records and credentials are
  never sent.
- Retrieved content is wrapped as data with an instruction not to follow embedded instructions. Output must be
  JSON; it is parsed strictly, citations to passages that weren't sent are dropped, unsupported answers are marked
  low confidence, and nothing is acted on automatically. People review and save drafts explicitly.
- Per-organisation daily limits.

## Browser security

- CSP with a per-request nonce and `strict-dynamic` for scripts, `frame-ancestors 'none'`, `base-uri 'none'`,
  `object-src 'none'`. API responses use `default-src 'none'`.
- HSTS (two years, preload) in production; `X-Content-Type-Options`, `Referrer-Policy`, COOP and CORP.
- Pages whose URL contains a secret token (reset, verification, invitations, vendor questionnaires) send
  `Referrer-Policy: no-referrer` and `Cache-Control: no-store`; reset and verification tokens are removed from the
  address bar on load.
- Spreadsheet exports neutralise formula injection.

## Operations

- Containers run as non-root, read-only, with all capabilities dropped and `no-new-privileges`.
- Database migrations run as the owner role in a separate one-shot container; the app never holds DDL rights.
- Daily encrypted backups of the database and evidence store (GPG AES-256), with retention.
- JSON logs with request IDs; Prometheus metrics at `/metrics` (not routed publicly) including failed logins,
  lockouts and blocked CSRF/Origin requests.

## Known limitations and planned work

- The master encryption key is an environment variable; KMS or HSM-backed keys are planned for the hosted service.
- Rate limits are per IP and per account; there's no CAPTCHA or bot detection yet.
- WebAuthn/passkeys are not yet supported (TOTP only).
- SCIM provisioning is not yet supported; SSO accounts are created just in time.
- An independent penetration test is required before general availability.
