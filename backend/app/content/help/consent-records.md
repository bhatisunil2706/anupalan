---
title: Consent records
section: DPDP and privacy
order: 30
summary: Versioned consent notices, a tamper-proof log of every grant and withdrawal from your website and apps, and a feed of withdrawals to act on.
routes: /dpdp/consent
---

Under the DPDP Act, consent must be free, specific, informed and unambiguous, and **withdrawing it must be as easy as giving it**. You must also be able to show what a person agreed to, and when. **Consent records** gives you exactly that.

## How it works

1. You write a **consent notice** with purposes, and publish it. Each published change creates a new version.
2. When someone agrees (or withdraws) on your website or app, your system sends a record to the platform's [Consent API](/docs/api#consent-api).
3. The platform keeps an **append-only log**: records can't be edited or deleted, not even by admins. Each record stores the person's ID in your system, the notice and version, the purposes, the source, the language and the time.
4. Your systems poll the **withdrawals feed** and stop processing for withdrawn purposes, including telling your processors.

## The three tabs

### Records

Totals for the last 30 days (consents, withdrawals, people on record, last record), the latest records, and **Look up a person by your user ID** to see their full consent history: what they agreed to, which notice version, when, and any withdrawals. **Export** downloads the log as CSV for auditors or for answering an access request.

You can also record consent given on paper or over a call centre line manually; the source is recorded as such.

### Consent notices

Each notice has:

- a **key** (for example `marketing` or `kyc-onboarding`) that your code refers to;
- a **title** and **notice text** (Markdown): what you collect, why, how to withdraw, and how to complain;
- **purposes**: each with an ID (used in the API), a label, and whether it's **required** for the service;
- **languages** offered. DPDP expects notices in English or any of the 22 languages of the Eighth Schedule, as the person chooses.

Edit as a draft, then **Publish** (admins). Published versions never change; publishing an edit creates the next version, and new records default to the latest published version.

### Connect your app

A step-by-step guide with copyable examples:

1. **Create an API key** with the `consent:write` scope (and `consent:read` for the systems that read the withdrawals feed) in **Settings → Security → API keys**.
2. **Send a record when someone agrees or withdraws.**
3. **Act on withdrawals** by polling the feed.

The full request and response formats are in the [API reference](/docs/api#consent-api).

## Automated check

Every day the platform checks that consent is being recorded and that withdrawals are captured, and records the result on **PRV-03** (consent capture) and **PRV-04** (withdrawal).

## Consent Managers

DPDP's registered Consent Managers start from 13 November 2026. Records that arrive through a Consent Manager can already carry its reference (`source: consent_manager`, `consent_manager_ref`). A direct integration will follow once the Board publishes the interface.
