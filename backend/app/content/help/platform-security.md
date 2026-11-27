---
title: How we protect your data
section: Reference
order: 20
summary: The security design of the platform itself - tenant isolation, sign-in, encryption, the audit trail, AI safeguards and known limitations. Useful for your own vendor reviews.
---

You'll keep sensitive information here: policies, evidence, people data and incidents. This page explains how the platform protects it. Your customers' security teams may ask for it when they review you as a vendor.

## Isolation between companies

Every table that holds a company's data uses PostgreSQL **row-level security**. The application connects with a database role that can't bypass it, and the company is set for each request from your server-side session. So even a bug in the application can't show one company's data to another. Application filters are a second layer on top.

## Signing in

- Passwords are hashed with **Argon2id**. They must be at least 12 characters and are checked for strength, personal information and known breaches (only a five-character hash prefix leaves the server).
- Accounts are locked after repeated failures, and the owner of the account is emailed.
- **Two-step verification** (TOTP) with replay protection and single-use recovery codes; organisations can require it.
- **Single sign-on** with Google, Microsoft, Okta or OIDC, using PKCE, state and nonce checks, and only for domains you've verified by DNS.
- Sessions are random tokens stored server-side (only their hash), can be revoked from the device list, and end after 12 hours or your idle timeout. Changing or resetting a password signs out other devices.
- Auditor access expires automatically.

See [Your account security](/docs/account-security) and [Sign-in and security settings](/docs/sign-in-security).

## Requests and the browser

- Every change request needs a CSRF token and a matching origin.
- Rate limits apply per address, with stricter limits on sign-in, password reset and public pages.
- A strict Content Security Policy with per-request nonces, HSTS, no framing, and no referrer on pages whose address contains a secret token.
- Spreadsheet exports are protected against formula injection.

## Evidence files

- Encrypted with **AES-256-GCM**, using a key unique to your company and bound to the file's storage location, so a file can't be moved between companies.
- File types are checked by content, executables are refused, and uploads can be virus-scanned with ClamAV.
- A **SHA-256 fingerprint** is taken at upload and checked on every download and in evidence packs; a changed file is refused and logged.
- Downloads are recorded in the audit log.
- Uploaded evidence counts only after a second person approves it. See [Evidence review](/docs/evidence-review).

## Secrets and integrations

- Integration credentials and webhook URLs are encrypted and never shown again after saving.
- API keys are stored as hashes, scoped to what they may do, and shown only once.
- Connections to addresses you provide (connectors, webhooks, data sources) must use HTTPS and, in production, can't reach private or internal addresses.
- Databases on your private network are scanned by an agent you run, which sends only categories, counts and masked examples.

## Audit trail

Every action is recorded in a per-company log in which each entry includes the hash of the previous one. The application can only add entries, never change them, and anyone can **Verify integrity** in Settings. See [Organisation settings](/docs/organisation-settings#audit-log).

## AI assistant

The assistant is **off** until your owner turns it on. Only policy and control text, framework requirements and the questions you upload are sent; people data, consent records and credentials never are. Evidence files are sent only if the owner separately turns on AI evidence checks. Everything the AI produces is a draft or advice that a person reviews; it never approves evidence or changes anything by itself. See [AI assistant](/docs/ai-assistant).

## Operations

- Containers run read-only, as non-root, with all privileges dropped.
- Database changes run in a separate container; the application never holds rights to alter the schema.
- HTTPS by default, encrypted daily backups, and monitoring of security events.
- Every change is tested and scanned for vulnerable dependencies, leaked secrets and insecure code before release.

## Known limitations

We'd rather you heard these from us:

- The master encryption key is held in an environment variable; hardware-backed key management is planned.
- Passkeys (WebAuthn) and SCIM user provisioning aren't supported yet.
- There's no CAPTCHA; protection against automated attacks relies on rate limits and lockouts.
- An independent penetration test is planned before general availability.

## Reporting a vulnerability

Report it privately through GitHub: [Report a vulnerability](https://github.com/bhatisunil2706/pramaanly/security/advisories/new) on the project's Security tab. Please don't open a public issue. We acknowledge reports within two business days and won't take action against good-faith research. Self-hosted installations publish this contact at `/.well-known/security.txt`.
