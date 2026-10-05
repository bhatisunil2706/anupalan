# Anupalan (working name)

India-first compliance automation. One set of controls, mapped to the **DPDP Act 2023 + DPDP Rules 2025**, the **CERT-In Directions (April 2022)**, **ISO/IEC 27001:2022** and **SOC 2**, with evidence collection, policies, risk, vendors and DPDP operations (data inventory, rights requests, breach clocks).

> "Anupalan" (अनुपालन, compliance) is a placeholder. Change it with `NEXT_PUBLIC_APP_NAME` and `APP_NAME`.

## What's in v0.1

| Area | What works |
| --- | --- |
| Accounts | Sign-up, sign-in, multiple organisations per user, invitations by link, roles (owner, admin, member, auditor read-only), audit log |
| Onboarding | Company profile, applicability flags (children's data, Significant Data Fiduciary, Consent Manager, infra provider, VASP), framework choice |
| Content | 4 frameworks, 217 requirements, 94 controls, every requirement mapped to at least one control (validated in tests), 8 policy templates |
| Controls | Status, owner, review dates, N/A with justification, evidence (file, link, note), health (passing / needs evidence / failing check), custom controls |
| Readiness | Per-framework score; conditional requirements drop out when they don't apply |
| Policies | Templates filled with your company name, editing with versioning, approval (auto-attaches evidence to mapped controls), staff acknowledgments |
| DPDP | Processing inventory with lawful ground and transfers (CSV export), rights requests with internal SLA and the 90-day legal cap |
| Incidents | CERT-In 6-hour clock, DPDP "without delay" steps and 72-hour Board report, investigation notes |
| Risk / vendors | 5x5 risk register with heat map; vendor tiers, DPA tracking, data location, review dates |
| Integrations | GitHub and AWS connectors (read-only). Passing checks become evidence; failing checks create tasks that auto-close when fixed. Credentials encrypted at rest. Worker re-runs every 6 hours |

## Run it

### Option A: Docker (simplest)

```bash
cp .env.example .env      # fill SECRET_KEY and ENCRYPTION_KEY for anything beyond your laptop
docker compose up --build
```

Open http://localhost:3000 and create a workspace. If port 3000 is taken, set `WEB_PORT` and `PUBLIC_URL` in `.env` (for example 3100).

### Option B: Local development

Requirements: Python 3.12+, Node 22+, PostgreSQL 16.

```bash
# Database
createdb app

# Backend (http://localhost:8000, API docs at /api/docs)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/app"
alembic upgrade head
uvicorn app.main:app --reload

# Integration worker (separate terminal, optional)
python -m app.worker

# Frontend (http://localhost:3000), separate terminal
cd frontend
npm install
npm run dev
```

The frontend proxies `/api/*` to the backend (`BACKEND_URL`, default `http://localhost:8000`), so the session cookie is first-party.

### Tests

```bash
createdb app_test
cd backend
DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/app_test" pytest -q   # 21 tests
ruff check app tests
python -m app.cli check-content                                               # mapping coverage only

cd ../frontend && npx tsc --noEmit && npm run build
```

## Project layout

```
backend/
  app/
    content/          Frameworks (YAML), control library + mappings, policy templates (Markdown)
    api/routes/       auth, org, frameworks, controls + evidence, work (tasks/policies/risks/vendors), dpdp, integrations, dashboard
    integrations/     Connector interface + GitHub, AWS
    services/         content loader, compliance engine (provisioning, health, readiness), policies, storage, audit
    models.py         SQLAlchemy models (global content vs tenant data)
    worker.py         Scheduled integration sync
  alembic/            Migrations
  tests/              API, tenant isolation, roles, deadlines, integrations
frontend/
  src/app/(auth)      Sign in, sign up, invitation, onboarding
  src/app/(app)       Dashboard, frameworks, controls, policies, integrations, DPDP, incidents, risks, vendors, tasks, settings
  src/components      UI kit, app shell, readiness seal
```

## How the compliance engine works

- **Global content** (frameworks, requirements, control templates, mappings) lives in `backend/app/content` and is loaded on startup (`python -m app.cli load-content` to reload). Loading fails if any requirement has no control.
- **Provisioning**: enabling a framework creates org controls for every template mapped to an applicable requirement. Requirements with a `condition` only apply when that profile flag is on.
- **Control health**: `not_applicable` → excluded; any failing automated check → `failing`; `implemented` + current evidence → `passing`; `implemented` without current evidence → `needs_evidence`.
- **Readiness**: a requirement is met when all its mapped controls are passing or not applicable.

## Adding a connector

Subclass `Connector` in `backend/app/integrations/`, declare `fields` and `tests` (each test lists the control codes it proves), implement `verify()` and `run()`, and register it in `integrations/__init__.py`. See `github.py` and its tests for the pattern.

## Before customer launch

These are known gaps, ordered roughly by priority:

1. **Content review.** All framework guidance is written in-house and marked `review_status: draft`. Have a privacy lawyer verify the DPDP and CERT-In references against the Gazette text, and an ISO 27001 Lead Auditor review the control mappings. ISO and AICPA text is intentionally not reproduced; keep it that way.
2. **Email.** Invitations return a copyable link. Add an email provider (SES Mumbai, Postmark) for invites, password reset (not built yet), deadline reminders and task notifications.
3. **MFA and SSO** for user accounts (TOTP, then SAML/OIDC). Password reset flow.
4. **Storage.** Evidence is stored on local disk. Switch `services/storage.py` to S3 in `ap-south-1` with per-tenant prefixes and KMS keys.
5. **Rate limiting** is in-process; move to Redis for more than one API instance.
6. **Database-level tenant isolation.** Isolation is enforced in the API (`get_owned`, `ensure_member`) and covered by tests. Add PostgreSQL row-level security as a second layer.
7. **More connectors**: Google Workspace, Microsoft 365 / Entra ID, Azure, GCP, an Indian HRMS (Keka or Darwinbox), MDM.
8. **AI assistant** (policy drafting, gap analysis, questionnaire answers) and **auditor workspace** (scoped auditor access, evidence requests, SoA export).
9. **Sector packs**: RBI, SEBI CSCRF, IRDAI.

## Licence and IP

This codebase is written from scratch and does not include code or content from other GRC products. Keep it that way: don't copy code, framework libraries or mapping files from AGPL or commercial projects. Check dependencies' licences before adding them (avoid GPL/AGPL in the product).
