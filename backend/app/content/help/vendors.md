---
title: Vendors
section: Risk and vendors
order: 20
summary: Your vendor inventory - risk tiers, data processing agreements, certificates with expiry tracking, reviews and security questionnaires.
routes: /vendors, /vendors/*
---

Your vendors are part of your security: a breach at your payroll provider or cloud host is your problem too. DPDP makes you responsible for what your processors do with personal data, and every framework asks you to assess suppliers (VEN-01 to VEN-03).

## Adding a vendor

**Add vendor** and record:

| Field | Guidance |
| --- | --- |
| Name, website, services | What they do for you |
| Risk tier | **Critical**: you can't operate without them, or they hold sensitive data at scale. **High**: access to confidential or personal data. **Medium**: limited access. **Low**: no access to your data or systems. |
| Data shared | Categories of data they get |
| Processes personal data | Tick if they're a DPDP data processor |
| DPA signed | Whether a data processing agreement is in place |
| Data location | Where they store your data |
| Certifications | ISO 27001, SOC 2 and so on |
| Status | Onboarding, Active or Offboarded |
| Owner, last assessed, next review | Who manages the relationship, and the review cycle |

When you mark a vendor's questionnaire as reviewed, the next review date is set by tier: critical and high vendors every 12 months, medium every 24 months, low vendors none. You can also set the date yourself. When a review falls due, a **Review vendor** task is created, and vendors due in the next 30 days show on the dashboard.

## Certificates and documents

On a vendor's page, upload documents with a **type** and **valid until** date: ISO 27001 certificate, SOC 2 report, data processing agreement, penetration test summary, cyber insurance or other. Vendors can also upload them while answering a questionnaire. The platform emails a reminder before a document expires and when it has expired.

## Security questionnaires

Send questionnaires from the vendor's page with **Send questionnaire**. The vendor answers through a secure link, without an account. The platform scores the answers, highlights critical gaps, reminds the vendor and records your review as evidence. See [Vendor questionnaires](/docs/vendor-questionnaires).

## Offboarding

When you stop using a vendor, set the status to **Offboarded**, get confirmation that your data was returned or deleted, upload that confirmation, and remove their access.
