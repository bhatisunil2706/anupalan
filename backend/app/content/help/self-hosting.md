---
title: Installing and running the platform
section: Administration
order: 40
summary: Run it on a laptop or a server with Docker - configuration, production hardening, email, storage, backups, upgrades and admin commands.
---

The platform runs as a set of Docker containers. This page is for the person who installs and operates it.

## What runs

| Container | Role |
| --- | --- |
| `web` | The Next.js web app on port 3000 (or `WEB_PORT`) |
| `backend` | The FastAPI application and API |
| `worker` | Background jobs: integration syncs every 6 hours, reminders and recurring tasks every 15 minutes, notifications every minute, AI jobs, evidence fingerprinting and link checks hourly |
| `db` | PostgreSQL 16 |
| `redis` | Rate limits and sign-in lockouts |
| `migrate` | Runs once at start: database upgrades, the restricted database role and content loading |
| `caddy`, `backup` | Production only: HTTPS and encrypted daily backups |

## Quick start on a laptop

Requirements: Docker Desktop.

~~~
cp .env.example .env
./start.sh
~~~

`start.sh` builds the images, upgrades the database, starts everything, loads the demo companies (once) and opens the browser. Sign in as `priya@paisasetu.example` with the password `Demo-Anupalan-2026!`. Run `./start.sh` again after pulling new code.

If port 3000 is taken, set `WEB_PORT` and `PUBLIC_URL` in `.env` (for example 3100 and `http://localhost:3100`).

## Configuration

All settings are environment variables in `.env`. The important ones:

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development` or `production` |
| `PUBLIC_URL` | The address people use, for links in emails |
| `SECRET_KEY` | Signs tokens. Required in production. |
| `ENCRYPTION_KEY` | Master key for evidence and credential encryption. Required in production. **Back it up separately from the database**: without it, evidence can't be decrypted. |
| `POSTGRES_PASSWORD`, `RUNTIME_DB_PASSWORD` | Passwords for the database owner and the restricted runtime role |
| `COOKIE_SECURE` | `true` behind HTTPS (set automatically in production) |
| `DOMAIN`, `ACME_EMAIL` | Production host name and the email for the automatic Let's Encrypt certificate |
| `STORAGE_BACKEND` | `local` (encrypted files in a Docker volume) or `s3` (plus `S3_BUCKET`, `S3_REGION`, `S3_KMS_KEY_ID`) |
| `CLAMAV_ADDRESS` | Optional ClamAV daemon (for example `clamav:3310`) to scan uploads for malware |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` | Email. Without `SMTP_HOST`, emails are written to the worker log. |
| `ANTHROPIC_API_KEY`, `AI_MODEL` | Optional: enables the AI assistant and AI evidence checks (each organisation's owner must still opt in) |
| `BACKUP_PASSPHRASE`, `BACKUP_DIR`, `BACKUP_KEEP_DAYS` | Encrypted backups (production) |
| `LOG_FORMAT`, `METRICS_TOKEN` | JSON logs, and a bearer token for Prometheus scraping of `/metrics` |

Generate secrets with:

~~~
python -c "import secrets; print(secrets.token_urlsafe(48))"            # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"            # RUNTIME_DB_PASSWORD
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # ENCRYPTION_KEY
~~~

To test email locally, run `docker compose --profile mail up`, set `SMTP_HOST=mailpit SMTP_PORT=1025 SMTP_STARTTLS=false` and open http://localhost:8025.

## Production

~~~
cp .env.example .env     # set every value marked REQUIRED, ENVIRONMENT=production, PUBLIC_URL=https://<DOMAIN>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
~~~

The production overlay adds Caddy with automatic HTTPS, encrypted daily backups, read-only containers running as non-root with all capabilities dropped, and startup checks: the app **refuses to start** with default secrets, without secure cookies or Redis, or with a database role that can bypass row-level security. Interactive API documentation is turned off in production.

Host it in an Indian region if you process Indian personal data and want to keep logs in India for CERT-In.

## Backups and restore

The `backup` container runs every 24 hours. It writes the database dump and the evidence store, each encrypted with AES-256 using `BACKUP_PASSPHRASE`, to `BACKUP_DIR`, and deletes backups older than `BACKUP_KEEP_DAYS` (default 30). Copy backups off the server, and store the passphrase and `ENCRYPTION_KEY` in your password manager.

To restore the database:

~~~
gpg --decrypt db-<timestamp>.sql.gz.gpg | gunzip | psql "$DATABASE_URL"
~~~

Test a restore at least once a quarter; that's evidence for OPS-06.

## Upgrades

Pull the new code and run `./start.sh` (laptop) or the production `up -d --build` command. The `migrate` container upgrades the database and reloads framework content before the app starts. Database upgrades are applied in order and can't be skipped.

## Admin commands

Run inside the migrate container, for example `docker compose run --rm migrate python -m app.cli check-content`:

| Command | What it does |
| --- | --- |
| `load-content` | Load or refresh frameworks, controls, templates, courses and questionnaires |
| `check-content` | Validate content (every requirement mapped, criteria present, questionnaires valid) and this documentation (every link resolves) |
| `sync-runtime-role` | Create or update the restricted database role and its row-level security grants |
| `seed-demo [--reset] [--password …]` | Load the demo companies (Paisa Setu, AarogyaLink, KiranaKart and FinBox (Demo)), adding any that are missing; `--reset` recreates them all and discards changes. Refuses to run in production. |
| `remove-demo` | Delete the demo companies and their users |
| `verify-audit` | Verify the hash chain of every organisation's audit log |

## Health and monitoring

- `GET /api/health` returns `{"status": "ok"}` when the backend is up.
- `GET /metrics` (with `Authorization: Bearer <METRICS_TOKEN>`) exposes Prometheus metrics, including security events such as account lockouts.
- Logs go to standard output; set `LOG_FORMAT=json` for your log platform.
