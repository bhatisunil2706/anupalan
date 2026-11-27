# Anupalan (working name)

**[▶ Live demo](https://bhatisunil2706.github.io/anupalan-demo/)**: click through the app with sample data for a fictional fintech. No sign-up; read-only.

India-first compliance automation. One set of controls, mapped to the **DPDP Act 2023 + DPDP Rules 2025**, the **CERT-In Directions (April 2022)**, the **RBI Cybersecurity Directions 2026** and other RBI rules (digital payments, payment aggregators, digital lending, IT outsourcing), **SEBI CSCRF**, **IRDAI** and **IFSCA** cyber guidelines, **ISO/IEC 27001:2022**, **SOC 2**, **NIST CSF 2.0**, **PCI DSS v4.0.1**, **ISO/IEC 42001**, **GDPR** and **HIPAA**, with evidence collection, policies, risk, vendors, training and DPDP operations (data inventory, consent records, rights requests, breach clocks).

> "Anupalan" (अनुपालन, compliance) is a placeholder. Change it with `NEXT_PUBLIC_APP_NAME` and `APP_NAME`.

## What's in v0.5

| Area | What works |
| --- | --- |
| Accounts | Sign-up with email verification, password reset, multiple organisations per user, invitations, roles (owner, admin, member, auditor with time-limited access) |
| Security | Two-step verification (TOTP + recovery codes), org-enforced MFA, SSO (Google, Microsoft Entra ID, Okta, any OIDC) with verified domains, server-side revocable sessions with a device list, breached-password blocking, PostgreSQL row-level security, per-company encrypted evidence, hash-chained audit log, strict CSP, CSRF tokens, Redis rate limits. See [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md) |
| Content | 18 frameworks, 771 requirements, 124 controls, every requirement mapped (validated in tests). India: DPDP, CERT-In. Indian financial regulators: RBI Cybersecurity Directions 2026 (tiered by NBFC layer; replaces the repealed 2023 IT Governance Direction, with automatic migration), RBI Digital Payment Security Controls 2026, RBI cyber resilience for non-bank PSOs (2024), RBI Payment Aggregators (2025), RBI Digital Lending (2025), RBI IT Outsourcing (2023), SEBI CSCRF (2024), IRDAI Cyber Security Guidelines (2026), IFSCA Cyber Security Guidelines (2025). Global: ISO 27001 (all clauses and 93 Annex A controls), SOC 2 (all five categories; Processing Integrity and Privacy switch on in the profile), NIST CSF 2.0 (all 106 outcomes), PCI DSS v4.0.1, ISO 42001. Other regions: GDPR, HIPAA Security and Breach Notification Rules. 8 policy templates, 12 training courses, 7 vendor questionnaires |
| Evidence assurance | **Second-person review**: uploaded evidence counts only after the control owner or an admin (not the uploader) approves it; review queue with a badge in the menu. **What the evidence must show**: 2-3 acceptance criteria for each of the 110 controls (editable per company); uploaders tick what their file shows and the control page shows which points are covered. **Automatic checks**: SHA-256 fingerprint at upload (verified on download), reused files from earlier periods, documents dated before the review period, unfinished templates, broken links. **AI evidence check** (opt-in, owner only): Claude reads the file against the criteria and gives an advisory verdict. **Auditor sampling**: reproducible random samples with pass/exception results and Excel export. Evidence packs contain only approved evidence, with who added and approved each item |
| Controls | Status, owner, review dates, N/A with justification, evidence (file, link, note), health (passing / needs evidence / failing check), custom controls. Edit any control's title, description, category and review frequency. Change the owner inline in the list or **assign many at once** (bulk owner / status); new owners get an email |
| Readiness | Per-framework score; conditional requirements drop out when they don't apply. Onboarding suggests frameworks by sector and only asks the profile questions for the frameworks picked |
| Risk register | Likelihood x impact heat map, treatment plans, linked controls. **Jira**: every new risk gets an issue automatically, edits are pushed, Jira status flows back (Done = treated, reopened = open), and issues matching a JQL filter are imported as risks |
| Policies | Four ways in: **upload** (Word .docx, PDF, Markdown, text, HTML), **paste from Google Docs or Word** (headings, lists, bold, tables kept), **write** in a visual editor (no Markdown needed; a Markdown view is there for power users), or start from a template. Owner and linked controls editable, versioning (editing an approved policy starts a new draft), approval (auto-attaches evidence), staff acknowledgments, download, AI drafting |
| DPDP | Processing inventory, rights requests with SLA and the 90-day legal cap, public request portal, **consent records** (versioned notices, append-only consent log, API for websites and apps, withdrawal feed, CSV export) |
| Incidents | CERT-In 6-hour clock, DPDP "without delay" steps and 72-hour Board report, financial regulator clocks (RBI, SEBI, IRDAI 6 hours; IFSCA 6 hours, 3 days, 30 days), reporting from the dashboard, a timeline and one email thread per incident |
| Training | 12 built-in courses (incl. UPI/KYC/'digital arrest' scams, AI at work, payment fraud for finance, privacy for support) with explained answers, shuffled options and 'phish or legit?' practice exercises. Assign by department from the HR roster; new joiners get the full window from their joining date. **Phishing simulations** (7 generic templates, company domains only, click tracking that ignores link scanners, auto-enrolment of clickers). Certificates, company-written courses (paste from Docs, video links, quiz builder), team progress by department, invite roster people without accounts, CSV evidence export, LMS import, weekly reminders, daily HR-03 check |
| Vendors | Risk tiers, DPAs, certificate expiry reminders. **Questionnaire library**: Standard Full (96 questions, 18 domains referenced to ISO 27001 and SOC 2), Standard Lite, Quick baseline, and add-ons for DPDP processors, GDPR Article 28, AI vendors and PCI DSS. Recommended by tier, core + add-ons in one email, a snapshot of the questions at send time, choice questions, N/A needs a reason. **Sent questionnaires** list with progress, reminders (manual and automatic 3 days before due, each with a fresh link) and cancel. Duplicate and customise any questionnaire, build your own, import from Excel/CSV, export questions or answers to Excel. Review creates VEN-01 evidence |
| Auditor workspace | Evidence requests with comments, submit / accept / send back, Statement of Applicability or requirements matrix (.xlsx), evidence pack (.zip with SHA-256 manifest) |
| AI assistant (opt-in) | Policy drafts, remediation plans from gaps, security questionnaire answers from your own policies with sources (Claude API) |
| Integrations | 25 integrations, 71 automated checks, all read-only except Jira issue creation (tasks and risks). Identity: Google Workspace, Microsoft 365, Okta. Cloud: AWS (incl. Security Hub, Inspector, Backup, log retention, key rotation, account separation), Azure, Google Cloud. Code: GitHub (incl. Dependabot fix deadlines), GitLab, Bitbucket. Vulnerabilities: Snyk, Tenable. Endpoints: CrowdStrike, SentinelOne, Intune, Jamf, Scalefusion (beta), Hexnode (beta). Monitoring and network: Datadog, Cloudflare. HR: Keka, Darwinbox, greytHR, Zoho People (all beta). IT ops: Freshservice, Jira |
| Automation coverage | Integrations page shows the share of controls that collect their own evidence and ranks which integration to connect next. Any other tool can push results through the evidence API (`POST /api/v1/evidence`, `evidence:write` key) |
| People & access | HR roster matched to identity accounts, leaver checks, quarterly access reviews |
| Data discovery | PostgreSQL, MySQL and S3 scanning for Indian identifiers; **self-hosted scanner agent** for private networks |
| Alerts | Email, Slack and Teams: failing checks, regulator deadlines, rights requests, tasks, renewals, overdue training, expiring vendor certificates |
| Documentation | In-app **Documentation** section (36 articles: getting started, every module, administration, self-hosting, API reference, platform security, glossary, FAQ) with search, an "On this page" outline, and a **Help** button on every page that opens the article for that page |
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

`.example` addresses are reserved and never receive email. Connector results in the demo are simulated, and so are the AI evidence check verdicts on Paisa Setu's review queue (set `ANTHROPIC_API_KEY` to run real checks on new uploads). The seed command refuses to run when `ENVIRONMENT=production`; `python -m app.cli remove-demo` deletes it all.

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

## Demo in GitHub Codespaces

Runs the whole app (web, API, worker, PostgreSQL, Redis) in a free GitHub Codespace, with the three demo companies.

1. **Optional but recommended:** set your own demo password. GitHub → your profile → **Settings → Codespaces → Secrets → New secret**: name `DEMO_PASSWORD`, any strong value, and give it access to this repository. Without it, demo logins use the public default password.
2. On the repository page: **Code → Codespaces → Create codespace on main**.
3. Wait for the first start (about 5 to 10 minutes: it builds the images and loads the demo data). The terminal ends with `Open: https://<name>-3000.app.github.dev`.
4. Open that link and sign in, for example as `priya@paisasetu.example` (Paisa Setu), with your `DEMO_PASSWORD`.

Sharing: the link needs a GitHub sign-in until port 3000 is **Public**. With `DEMO_PASSWORD` set, the Codespace makes it public automatically; otherwise, in the **Ports** tab, right-click 3000 → **Port Visibility → Public**. Anyone with a public link can reach the sign-in page, so use only demo data there.

Good to know:

- A Codespace stops after about 30 minutes without activity. Reopen it from **Code → Codespaces** and the app restarts; the link and the demo data stay the same. A new Codespace gets a new link.
- GitHub Free includes 120 core hours a month (about 60 hours on the standard 2-core machine) and 15 GB of storage. Stop or delete Codespaces you aren't using.
- `.devcontainer/setup.sh` writes `.env` with this Codespace's address and freshly generated secrets; the app runs in development mode (demo use only, not for real data).

## Live demo site

The public demo at https://bhatisunil2706.github.io/anupalan-demo/ is a static, read-only build of the real interface with recorded sample data. See [demo/README.md](demo/README.md) to update it.

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

## Editing the documentation

Articles are Markdown files in `backend/app/content/help/`, with front matter: `title`, `section` (one of the sections in `app/services/help.py`), `order`, `summary` and optionally `routes` (app pages the **Help** button should open this article from, for example `/controls, /controls/*`). Link to other articles as `/docs/<slug>#<heading>`. `python -m app.cli check-content` and the tests fail if any link or heading anchor doesn't resolve.

## Before customer launch

1. **Content review.** Framework guidance, training courses and questionnaires are written in-house and marked draft. Have a privacy lawyer verify DPDP, CERT-In and GDPR references, a banking/securities compliance specialist map the RBI and SEBI packs to paragraph numbers, a QSA review PCI DSS, a HIPAA specialist review HIPAA (watch the 2025 Security Rule update), and an ISO 27001/42001 Lead Auditor review the control mappings. ISO, AICPA and PCI SSC text is intentionally not reproduced.
2. **Real-tenant connector tests.** Every connector is built from official API docs and tested with simulated responses. Test each against a real account before customers rely on it. Keka and Darwinbox field mappings need checking against customer datasets.
3. **Independent penetration test** and an external review of [docs/security.md](docs/security.md).
4. **Key management.** Move the master encryption key to AWS KMS (or an HSM) for the hosted service.
5. **DPDP Consent Manager integration** once the Board publishes the interface (registration opens November 2026).
6. **Sector packs**: IRDAI Information and Cyber Security Guidelines; deeper RBI and SEBI paragraph mapping.
7. **Passkeys (WebAuthn) and SCIM provisioning.**

## Licence and IP

This codebase is written from scratch and does not include code or content from other GRC products. Keep it that way: don't copy code, framework libraries or mapping files from AGPL or commercial projects. Check dependencies' licences before adding them (avoid GPL/AGPL in the product).
