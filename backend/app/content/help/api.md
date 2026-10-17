---
title: API reference
section: Reference
order: 10
summary: Connect your own systems - authentication with API keys, the consent API, the evidence push API and the scanner API, with examples and error codes.
---

The platform has a small machine API for the things your own systems need to send or read automatically. Everything else is done in the web app.

All endpoints are under `https://<your address>/api`. Requests and responses are JSON, and times are ISO 8601 with a timezone (for example `2026-10-17T09:30:00+05:30`).

> Interactive API documentation (Swagger) is available at `/api/docs` on development installations only. It's turned off in production to avoid exposing the API surface.

## Authentication

Create an API key in **Settings → Security → API keys** (admins), choosing only the scopes the system needs. Send it as a bearer token:

~~~
Authorization: Bearer anp_xxxxxxxxxxxxxxxxxxxxxxxx
~~~

| Scope | Endpoints |
| --- | --- |
| `consent:write` | `POST /v1/consent/events` |
| `consent:read` | `GET /v1/consent/principals/{id}`, `GET /v1/consent/events` |
| `evidence:write` | `POST /v1/evidence` |
| `scanner:write` | `POST /v1/scanner/findings` |

A key belongs to one organisation and can only see that organisation's data. The key is shown once; only a hash is stored. Revoked or expired keys are rejected immediately. Every call made with a key is attributed to the key's prefix in the audit log. See [Sign-in and security settings](/docs/sign-in-security#api-keys).

Keep keys on servers only. Never put a key in a web page or mobile app: send consent events from your backend.

## Consent API

Record consent from your website, app or call centre, check what a person has consented to, and pick up withdrawals. Set up your notices first: see [Consent records](/docs/consent-records).

### Record a consent event

`POST /v1/consent/events` (scope `consent:write`)

~~~
curl -X POST https://<your address>/api/v1/consent/events \
  -H "Authorization: Bearer $ANUPALAN_KEY" -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_20261017_000123",
    "principal_id": "cust_88412",
    "notice_key": "app-signup",
    "action": "granted",
    "purposes": ["account", "marketing"],
    "source": "web",
    "language": "hi"
  }'
~~~

| Field | Required | Notes |
| --- | --- | --- |
| `event_id` | Yes | Your unique ID for the event. Sending the same ID again is safe: the original is returned with status 200 instead of 201. |
| `principal_id` | Yes | Your identifier for the person (a customer ID, not their email if you can avoid it) |
| `notice_key` | Yes | The key of a published notice |
| `notice_version` | No | Defaults to the version currently published |
| `action` | Yes | `granted` or `withdrawn` |
| `purposes` | For `granted` | Purpose IDs from the notice. Every required purpose must be included. For `withdrawn`, an empty list withdraws all purposes. |
| `source` | No | `web`, `app`, `api` (default), `import`, `consent_manager`, `call_centre` or `paper` |
| `language` | No | Language the notice was shown in (default `en`) |
| `occurred_at` | No | When it happened, with a timezone. Defaults to now; can't be in the future. |
| `consent_manager_ref` | No | Reference from a registered Consent Manager, if one was used |
| `metadata` | No | Up to about 4 KB of your own context (for example the page or app version) |

Events can't be edited or deleted: the record is an append-only history, which is what makes it evidence.

### Check a person's consent

`GET /v1/consent/principals/{principal_id}` (scope `consent:read`) returns the current state per notice:

~~~
{
  "principal_id": "cust_88412",
  "consents": {
    "app-signup": {"version": 3, "purposes": ["account"], "updated_at": "2026-10-17T09:30:00+05:30"}
  }
}
~~~

Check this before processing for a purpose that needs consent, such as marketing.

### Pick up changes and withdrawals

`GET /v1/consent/events?since=<time>&action=withdrawn&limit=500` (scope `consent:read`) returns events received after `since`, oldest first (up to 1,000 per call), and `next_since` to use in your next call. Poll it from the systems that must stop processing when someone withdraws, as DPDP section 6(6) requires.

## Evidence API

Push the results of checks your own tools run (CI pipelines, backup jobs, scripts, a SIEM) so they count as evidence, just like built-in [integrations](/docs/integrations).

`POST /v1/evidence` (scope `evidence:write`)

~~~
curl -X POST https://<your address>/api/v1/evidence \
  -H "Authorization: Bearer $ANUPALAN_KEY" -H "Content-Type: application/json" \
  -d '{
    "check": "backup-restore-test",
    "title": "Monthly database restore test",
    "control_codes": ["OPS-06"],
    "status": "pass",
    "summary": "Restored prod snapshot to staging in 14 minutes; row counts match.",
    "source": "Jenkins",
    "details": {"job": "restore-test", "build": 812}
  }'
~~~

| Field | Notes |
| --- | --- |
| `check` | Your stable ID for the check: lowercase letters, digits, `.`, `-` or `_` |
| `title` | Shown on the control |
| `control_codes` | One or more control codes in your organisation (for example `OPS-06`); unknown codes are rejected |
| `status` | `pass` or `fail` |
| `summary`, `source`, `details` | What happened, the tool name shown as the source, and up to 20 KB of supporting data |

A **pass** becomes automated evidence on the listed controls. A **fail** marks the check as failing and opens a Fix task for the control owner, who is notified. Send the result every time the check runs, so the evidence stays fresh.

## Scanner API

`POST /v1/scanner/findings` (scope `scanner:write`) is used by the self-hosted scanner agent to report what it found in databases on your private network. You don't normally call it yourself: see [Data discovery](/docs/data-discovery). The agent sends only categories, counts and masked examples, and the platform masks examples again regardless.

## Errors

| Status | Meaning |
| --- | --- |
| 200 / 201 | Success (200 for a repeated consent `event_id`) |
| 401 | Missing, invalid, revoked or expired API key |
| 403 | The key doesn't have the scope this endpoint needs |
| 404 | Not found |
| 422 | The request is invalid; `detail` says why (for example an unknown notice, purpose or control code) |
| 429 | Too many requests; wait and retry |

Errors are returned as `{"detail": "…"}`. Retry 5xx errors and 429 with backoff; don't retry 4xx errors without fixing the request. Consent events are safe to retry because of `event_id`.

## Public pages

These pages are used by people outside your organisation and need no key: the vendor questionnaire link, the [public privacy request page](/docs/rights-requests#the-public-privacy-request-page), and phishing simulation landing pages. They're rate-limited and only reveal what the link holder is entitled to see.
