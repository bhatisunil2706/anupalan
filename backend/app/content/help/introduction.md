---
title: Introduction
section: Get started
order: 1
summary: What the platform does, how its parts fit together, and what is automated versus what your team does.
---

Anupalan is a compliance automation platform built for Indian companies first. It helps you get and stay compliant with India's **Digital Personal Data Protection (DPDP) Act**, the **CERT-In Directions**, sector rules from **RBI** and **SEBI**, and international standards such as **ISO 27001**, **SOC 2**, **NIST CSF**, **PCI DSS**, **GDPR** and **HIPAA**. It does this from one place, with one set of work.

If you have never done compliance before, read this page and [Key concepts](/docs/concepts). They explain the few ideas everything else builds on.

## What the platform does for you

Compliance work usually means four things, and the platform covers each of them:

1. **Knowing what you must do.** Each framework is broken into requirements, written in plain language. The platform turns those into a single list of **controls**: concrete things your company does, such as "MFA is enforced for everyone" or "access is reviewed every quarter".
2. **Doing it and proving it.** For each control you record how it works and attach **evidence** (a screenshot, an export, a signed document). Where you connect your systems (AWS, Google Workspace, GitHub and 22 others), the evidence is collected automatically and checked every few hours.
3. **Running the ongoing operations.** Policies with approval and staff acknowledgment, security training and phishing tests, access reviews, vendor due diligence, the risk register, and the DPDP operations: data inventory, consent records, rights requests and breach handling.
4. **Passing the audit.** Auditors get their own time-limited accounts to request evidence, test samples, and download a verified evidence pack and Statement of Applicability.

## How the parts fit together

~~~
Frameworks (DPDP, ISO 27001, SOC 2 …)
   └─ Requirements (e.g. ISO 27001 A.5.17 "Authentication information")
        └─ mapped to Controls (e.g. ACC-08 "Password and secrets management")
             ├─ Evidence: files, links, notes, automated check results
             ├─ Owner, status and review frequency
             └─ Tasks when something needs doing
                  ↓
           Control health  →  Framework readiness %
~~~

The important design choice: **one control can satisfy many frameworks**. Enforcing MFA counts for DPDP, ISO 27001, SOC 2, NIST CSF, PCI DSS and HIPAA at once, so you do the work once. When you turn on a new framework, the platform adds only the controls you don't have yet.

## What is automated and what isn't

| Automated by the platform | Done by your team, made easy by the platform |
| --- | --- |
| Checks from 25 integrations, every 6 hours, with evidence saved automatically | Writing and approving policies (templates, upload, or AI drafts) |
| Failing checks turned into tasks and alerts | Deciding how each control works in your company |
| Reminders for expiring evidence, overdue tasks, legal deadlines | Uploading evidence that no system can provide (minutes, signed forms) |
| Leaver checks: people who left but still have accounts | Reviewing and approving evidence uploaded by others |
| Training assignment, reminders, phishing simulations and the HR-03 check | Taking training; responding to incidents and rights requests |
| CERT-In 6-hour and DPDP Board clocks on incidents | Making risk and vendor decisions |
| Vendor questionnaire sending, scoring and reminders | Working with your auditor |
| Automatic checks on uploaded evidence, and an optional AI check | |

The **Automation coverage** panel on the [Integrations](/docs/integrations) page shows how much of your control set runs itself, and what to connect next.

## Who uses it

| Role | Typical person | What they do |
| --- | --- | --- |
| Owner | Founder, CEO or CTO | Everything, including billing-level decisions such as turning on AI and single sign-on |
| Admin | Head of security, compliance lead | Runs the programme: settings, approvals, assignments, integrations |
| Member | Engineers, HR, finance, managers | Owns controls, uploads evidence, completes tasks and training |
| Auditor | External auditor (time-limited) | Reads everything, raises evidence requests, tests samples |

See [Roles and permissions](/docs/roles-and-permissions) for the full list.

## Where to go next

- [Your first 30 days](/docs/first-steps): a practical plan from sign-up to audit-ready.
- [Key concepts](/docs/concepts): control health, readiness and evidence validity explained.
- [Frameworks](/docs/frameworks): which frameworks apply to you.
