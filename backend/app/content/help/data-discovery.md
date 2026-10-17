---
title: Data discovery
section: DPDP and privacy
order: 40
summary: Scan databases and storage buckets for Indian and other personal data, safely, and turn findings into data inventory entries.
routes: /dpdp/discovery
---

You can't protect personal data you don't know you have. **Data discovery** scans your databases and storage for personal data (Aadhaar and PAN numbers, phone numbers, UPI IDs and more) and shows where it is, so you can complete your [data inventory](/docs/data-inventory) and apply the right controls.

## What it detects

Detection combines **column names** (such as `aadhaar_no`, `dob` or `mobile`) with **value patterns** checked on sampled values:

| Category | Detected by |
| --- | --- |
| Aadhaar number | Value pattern (12 digits, not starting 0 or 1) and column names |
| PAN | Value pattern (format AAAPA1234A) and column names |
| GSTIN | Value pattern |
| Payment card number | Value pattern |
| UPI ID | Value pattern with known UPI handles (okaxis, ybl, paytm and others) |
| Phone number | Indian mobile number pattern and column names |
| Email address | Value pattern and column names |
| IFSC code | Value pattern |
| Passport, voter ID, date of birth, address, name, bank account, gender | Column names |
| Health and biometric data | Column names (diagnosis, blood group, fingerprint and similar) |

## What leaves your systems

Scans are **read-only** and **sampled**: up to 200 rows per table across up to 300 tables, or up to 200 objects (256 KB each) in a bucket. Only the **category, counts and masked examples** are stored, never raw values. For example, an Aadhaar number is kept only as `XXXX XXXX 1234`.

## Two ways to scan

### From the platform (direct)

**Add data source**: give it a name and choose PostgreSQL, MySQL or Amazon S3, then enter connection details for a **read-only** user (database host, port, database, username, password; or bucket, prefix, region and an access key). Credentials are encrypted. Click **Scan** to run it.

In production the platform only connects to public addresses. Databases on private networks need the agent.

### Self-hosted scanner agent (private networks)

For databases inside your network, run the scanner agent there. It reads data locally and sends only categories, counts and masked examples. The platform masks examples again whatever the agent sends.

1. Create an API key with the `scanner:write` scope.
2. Create an environment file:

~~~
ANUPALAN_URL=https://app.yourcompany.com
ANUPALAN_API_KEY=anp_...
SCAN_NAME=orders-db (prod)
SCAN_KIND=postgres
SCAN_HOST=10.0.3.12
SCAN_PORT=5432
SCAN_DATABASE=orders
SCAN_USERNAME=readonly_scanner
SCAN_PASSWORD=...
~~~

3. Run it with Docker:

~~~
docker run --rm --env-file scan.env anupalan/backend python -m app.agent
~~~

For S3 use `SCAN_KIND=s3` with `SCAN_BUCKET`, `SCAN_PREFIX`, `SCAN_REGION`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Set `SCAN_DRY_RUN=1` to print the report instead of sending it. Schedule it with cron to keep findings current.

## Findings

Findings are grouped by source and table or object, with the categories found, how many sampled values matched, and masked examples. Select findings and **Add to data inventory** to create or update a processing activity with those systems and data categories.
