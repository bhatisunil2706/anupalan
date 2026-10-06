# Anupalan (working name)

India-first compliance automation. One set of controls, mapped to the **DPDP Act 2023 + DPDP Rules 2025**, the **CERT-In Directions (April 2022)**, **ISO/IEC 27001:2022** and **SOC 2**, with evidence collection, policies, risk, vendors, training and DPDP operations (data inventory, consent records, rights requests, breach clocks).

> "Anupalan" (अनुपालन, compliance) is a placeholder. Change it with `NEXT_PUBLIC_APP_NAME` and `APP_NAME`.

## What's in v0.3

| Area | What works |
| --- | --- |
| Accounts | Sign-up with email verification, password reset, multiple organisations per user, invitations, roles (owner, admin, member, auditor with time-limited access) |
| Security | Two-step verification (TOTP + recovery codes), org-enforced MFA, SSO (Google, Microsoft Entra ID, Okta, any OIDC) with verified domains, server-side revocable sessions with a device list, breached-password blocking, PostgreSQL row-level security, per-company encrypted evidence, hash-chained audit log, strict CSP, CSRF tokens, Redis rate limits. See [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md) |
| Content | 4 frameworks, 217 requirements, 94 controls, every requirement mapped (validated in tests), 8 policy templates, 4 training courses, 2 vendor questionnaires |
| Controls | Status, owner, review dates, N/A with justification, evidence (file, link, note), health (passing / needs evidence / failing check), custom controls |
| Readiness | Per-framework score; conditional requirements drop out when they don't apply |
| Policies | Templates, versioning, approval (auto-attaches evidence), staff acknowledgments, AI drafting |
| DPDP | Processing inventory, rights requests with SLA and the 90-day legal cap, public request portal, **consent records** (versioned notices, append-only consent log, API for websites and apps, withdrawal feed, CSV export) |
| Incidents | CERT-In 6-hour clock, DPDP "without delay" steps and 72-hour Board report |
| Training | Built-in courses with quizzes (security essentials, DPDP basics, phishing, secure development), required or optional, renewal cycles, team report, import from another LMS, daily HR-03 check |
| Vendors | Risk tiers, DPAs, **questionnaires by link** (vendor answers without an account and uploads certificates), scoring with critical gaps, review creates VEN-01 evidence, certificate expiry reminders |
| Auditor workspace | Evidence requests with comments, submit / accept / send back, Statement of Applicability or requirements matrix (.xlsx), evidence pack (.zip with SHA-256 manifest) |
| AI assistant (opt-in) | Policy drafts, remediation plans from gaps, security questionnaire answers from your own policies with sources (Claude API) |
| Integrations | Google Workspace, Microsoft 365, Okta, AWS, Azure, Google Cloud, GitHub, GitLab, Intune, Jamf, Keka (beta), Darwinbox (beta), Jira (two-way task sync). All read-only except Jira issue creation |
| People & access | HR roster matched to identity accounts, leaver checks, quarterly access reviews |
| Data discovery | PostgreSQL, MySQL and S3 scanning for Indian identifiers; **self-hosted scanner agent** for private networks |
| Alerts | Email, Slack and Teams: failing checks, regulator deadlines, rights requests, tasks, renewals, overdue training, expiring vendor certificates |
| Operations | Docker Compose with a migration/runtime database role split, Caddy TLS, encrypted backups, read-only containers, `/metrics`, JSON logs, CI with security scanning |

## Run it

### Option A: Docker (simplest)

```bash
cp .env.example .env      # fill SECRET_KEY and ENCRYPTION_KEY for anything beyond your laptop
docker compose up --build
```

Open http://localhost:3000. If port 3000 is taken, set `WEB_PORT` and `PUBLIC_URL` in `.env` (for example 3100).

### Demo data

Three demo companies with a login per role (password `Demo-Anupalan-2026!` unless you pass `--password`):

```bash
docker compose run --rm migrate python -m app.cli seed-demo          # add --reset to recreate
```

| Company | Owner | Admin | Member | Auditor |
| --- | --- | --- | --- | --- |
| Paisa Setu Fintech (DPDP, CERT-In, ISO 27001, SOC 2; about 70% ready) | priya@paisasetu.example | arjun@paisasetu.example | neha@paisasetu.example | kavya@paisasetu.example |
| AarogyaLink Health (DPDP, ISO 27001; about 45%) | sameer@aarogyalink.example | lakshmi@aarogyalink.example | imran@aarogyalink.example | deepa@aarogyalink.example |
| KiranaKart Commerce (DPDP, CERT-In, SOC 2; just starting) | rajesh@kiranakart.example | sunita@kiranakart.example | amit@kiranakart.example | none |

`.example` addresses are reserved and never receive email. Connector results in the demo are simulated. The seed command refuses to run when `ENVIRONMENT=production`; `python -m app.cli remove-demo` deletes it all.

### Production

```bash
cp .env.example .env      # set every value marked REQUIRED, ENVIRONMENT=production, PUBLIC_URL=https://<DOMAIN>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This adds Caddy (automatic HTTPS), encrypted daily backups, read-only containers and the production startup checks: the app refuses to start with default secrets, without HTTPS cookies or Redis, or with a database role that can bypass row-level security.

### Option B: Local development

Requirements: Python 3.12+, Node 22+, PostgreSQL 16, Redis (optional locally).

```bash
createdb app
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/app"
alembic upgrade head && python -m app.cli load-content
uvicorn app.main:app --reload            # API docs at http://localhost:8000/api/docs
python -m app.worker                     # separate terminal: syncs, reminders, alerts, AI jobs

cd ../frontend && npm install && npm run dev
```

Locally the app connects as your own database user, which bypasses row-level security, and startup logs a warning. To test with RLS on, run `RUNTIME_DB_PASSWORD=... python -m app.cli sync-runtime-role` and connect as `app_runtime`.

### Tests

```bash
createdb app_test
cd backend
DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/app_test" pytest -q   # runs the app as an RLS-restricted role
ruff check app tests && bandit -q -r app -c pyproject.toml && pip-audit -r requirements.txt
python -m app.cli check-content
cd ../frontend && npx tsc --noEmit && npm run build
```

## Project layout

```
backend/
  app/
    content/          Frameworks, control library + mappings, policy templates, training courses, questionnaires
    api/routes/       auth, security_admin, org, frameworks, controls, work, dpdp, consent, training, vendor_dd,
                      auditor, ai, integrations, automation, portal, scanner_api, dashboard
    integrations/     13 connectors with a shared interface
    services/         compliance engine, checks, reminders, encrypted storage, sessions, SSO, audit chain, AI, demo
    rls.py            Row-level security policies and the restricted runtime role
    agent.py          Self-hosted personal data scanner
    worker.py         Scheduled syncs, reminders, alert delivery, AI jobs
  alembic/            Migrations
  tests/              Security, tenant isolation, roles, features, connectors, AI (mocked)
frontend/
  src/proxy.ts        Per-request CSP nonces
  src/app/(auth)      Sign in (MFA, SSO), sign up, password reset, email verification, invitation, onboarding
  src/app/(app)       Dashboard, compliance, audit requests, training, AI assistant, automation, DPDP, risk, vendors,
                      account security, settings
  src/app/q, src/app/p  Public vendor questionnaire and privacy request portal
deploy/               Caddyfile, backup script
docs/security.md      Threat model and security design
```

## How the compliance engine works

- **Global content** (frameworks, requirements, control templates, mappings, courses, questionnaires) lives in `backend/app/content` and is loaded by `python -m app.cli load-content`. Loading fails if any requirement has no control.
- **Provisioning**: enabling a framework creates org controls for every template mapped to an applicable requirement. Requirements with a `condition` only apply when that profile flag is on.
- **Control health**: `not_applicable` → excluded; any failing automated check → `failing`; `implemented` + current evidence → `passing`; `implemented` without current evidence → `needs_evidence`.
- **Readiness**: a requirement is met when all its mapped controls are passing or not applicable.

## Adding a connector

Subclass `Connector` in `backend/app/integrations/`, declare `fields` and `tests` (each test lists the control codes it proves), implement `verify()` and `run()`, and register it in `integrations/__init__.py`. Validate customer-supplied hosts with `guarded_base_url`. See `okta.py` and `tests/test_connectors.py` for the pattern.

## Before customer launch

1. **Content review.** Framework guidance, training courses and questionnaires are written in-house and marked draft. Have a privacy lawyer verify DPDP and CERT-In references against the Gazette text, and an ISO 27001 Lead Auditor review the control mappings. ISO and AICPA text is intentionally not reproduced.
2. **Real-tenant connector tests.** Every connector is built from official API docs and tested with simulated responses. Test each against a real account before customers rely on it. Keka and Darwinbox field mappings need checking against customer datasets.
3. **Independent penetration test** and an external review of [docs/security.md](docs/security.md).
4. **Key management.** Move the master encryption key to AWS KMS (or an HSM) for the hosted service.
5. **DPDP Consent Manager integration** once the Board publishes the interface (registration opens November 2026).
6. **Sector packs**: RBI, SEBI CSCRF, IRDAI.
7. **Passkeys (WebAuthn) and SCIM provisioning.**

## Licence and IP

This codebase is written from scratch and does not include code or content from other GRC products. Keep it that way: don't copy code, framework libraries or mapping files from AGPL or commercial projects. Check dependencies' licences before adding them (avoid GPL/AGPL in the product).
