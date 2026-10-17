---
title: Data inventory
section: DPDP and privacy
order: 20
summary: Your record of processing - every activity that uses personal data, its purpose, lawful ground, retention, processors and transfers.
routes: /dpdp/inventory
---

The **data inventory** (also called a record of processing activities) lists every way your organisation uses personal data. It's the foundation for DPDP notices, rights requests, breach assessments and the PRV-01 control, and auditors under GDPR and ISO 27701 ask for the same thing.

## What to record for each processing activity

| Field | What to enter | Example |
| --- | --- | --- |
| Processing activity name | A short name | Customer onboarding (KYC) |
| Description | What happens | We verify identity and address before opening an account |
| Systems | Where the data lives | Core app (Postgres), S3 document store, Signzy |
| Data principals | Whose data | Customers, applicants |
| Data categories | What data | Name, phone, PAN, Aadhaar (masked), address, selfie |
| Purposes | Why | Account opening and regulatory KYC |
| Lawful ground | Consent, or a legitimate use under DPDP s.7 | Legitimate use |
| Which legitimate use | Required when the ground is legitimate use | Compliance with law (RBI KYC Master Direction) |
| Retention period | How long, and the trigger | 5 years after account closure |
| Processors | Vendors that process it | Signzy, AWS |
| Stored or accessed outside India | Tick if so, and list the countries | No |
| Includes children's data (under 18) | Triggers the children's data rules | No |
| Owner | Who is responsible | Head of Operations |
| Last reviewed | When it was last checked | 2026-09-30 |

## Building it quickly

1. Start with your main products and internal functions: customer accounts, payments, support, marketing, HR and payroll, recruitment.
2. Use [Data discovery](/docs/data-discovery) to scan your databases and storage. Its findings can be added to the inventory in one click with **Add to data inventory**.
3. Ask each system owner to check their activities.
4. Review the inventory at least yearly, and whenever you launch a feature that uses personal data, then update **Last reviewed**.

## How it's used elsewhere

- **Rights requests**: the inventory tells you where to look for a person's data.
- **Incidents**: it helps you work out whose data, and which categories, were affected.
- **Cross-border transfers**: activities marked as stored outside India feed PRV-13.
- **Evidence**: an export of the inventory is the evidence for PRV-01.
