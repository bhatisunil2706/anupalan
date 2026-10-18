---
title: Frequently asked questions
section: Reference
order: 40
summary: Quick answers to the questions people ask most - about readiness, evidence, audits, DPDP, AI and data.
---

## Getting started

### I'm not a compliance expert. Where do I begin?

Follow [First steps](/docs/first-steps). In short: turn on the frameworks your customers or regulators ask for, answer the profile questions, connect your cloud and identity systems, adopt the policy templates, assign control owners, and work through **Tasks**. The platform tells you what's missing at every step.

### Which framework should I start with?

If you process personal data of people in India, **DPDP** applies to you by law. **CERT-In** incident reporting applies to almost every Indian company. Customers selling to enterprises usually also ask for **ISO 27001** or **SOC 2**. Because controls are shared, work done for one framework counts towards the others. See [Frameworks](/docs/frameworks).

### Does using this platform make us compliant or certified?

No tool can do that alone. The platform organises the work, collects and checks evidence, and shows your gaps; your team still has to run the controls, and certification comes from an independent auditor. What the platform does is make that audit faster and the evidence trustworthy.

## Readiness and evidence

### Why did my readiness go down?

Usually because evidence expired, an integration check started failing, uploaded evidence is still waiting for approval, or a profile answer added new requirements. Open the framework and look for controls that are no longer healthy. See [Key concepts](/docs/concepts#how-readiness-is-calculated).

### I uploaded evidence but the control is still not healthy.

Uploaded evidence counts only after a second person approves it. Check **Evidence review** in the sidebar, or ask the control owner or an admin to review it. See [Evidence review](/docs/evidence-review).

### How does the platform know evidence is genuine?

It combines several safeguards: a second person approves it against written acceptance criteria; automatic checks flag reused, outdated, template or broken evidence; the optional AI check compares the file to the criteria; every file is fingerprinted so later changes are detected; and auditors re-test a reproducible random sample. Evidence from integrations comes straight from the source system.

### Can I approve my own evidence?

Only if nobody else in your company could; that approval is flagged for the auditor. Auditors can't approve evidence.

### How often do I need fresh evidence?

Each control has a review frequency (for example quarterly or yearly), and evidence expires after it. The platform creates a renewal task before that happens. See [Controls](/docs/controls#review-frequency).

## Audits

### How do I work with my auditor here?

Invite them with the **auditor** role and an access period. They can read everything relevant, raise evidence requests, test samples and download exports, but can't change your data. See [Audit workspace](/docs/audit-workspace).

### What does the evidence pack contain?

All current approved evidence for a framework, organised by control, with a manifest of each file's fingerprint and whether it's unchanged. See [Audit workspace](/docs/audit-workspace#evidence-pack).

## DPDP and privacy

### Do we need a consent record for every user?

For processing that relies on consent, yes: you must be able to show what notice a person saw and what they agreed to. Send consent events from your systems with the [Consent API](/docs/api#consent-api). Processing for other lawful purposes, such as employment, doesn't need consent but should still be in your [data inventory](/docs/data-inventory).

### How fast must we answer a rights request?

Within the service level you set (30 days by default). The platform starts the clock when the request arrives and reminds the assignee before it's due. See [Rights requests](/docs/rights-requests).

### We had a data breach. What do I do first?

Report it straight away with **Report incident** on the dashboard; anyone except auditors can. You'll get every update by email, in one thread. The platform starts the CERT-In and Data Protection Board clocks and lists what to do and who to tell. See [Incidents and breaches](/docs/incidents).

## AI and data

### Does the AI see our data?

Only if your owner turns it on, and then only policy and control text, framework requirements and the questions you upload. People data, consent records and credentials are never sent. Evidence files are sent only if AI evidence checks are separately turned on. See [AI assistant](/docs/ai-assistant).

### Where is our data stored, and who can see it?

On the server where the platform is installed; for self-hosted installations, that's your own infrastructure. Each company's data is isolated by the database itself, evidence is encrypted with a company-specific key, and every access is logged. See [How we protect your data](/docs/platform-security).

### Can we connect our own tools?

Yes: there are built-in [integrations](/docs/integrations) and [Jira](/docs/jira), and the [Evidence API](/docs/api#evidence-api) lets any script or CI job send check results.

## Accounts

### I'm locked out.

After 10 failed attempts your account locks for an hour. Use **Forgot password** to get back in sooner. If you lost your authenticator, sign in with one of your recovery codes and set up two-step verification again. If you've lost the codes too, contact whoever runs your installation: by design, there's no self-service way around two-step verification. See [Your account security](/docs/account-security).

### How do I remove someone who left?

Remove them from **Settings → Team**, and use **People & accounts** to make sure their access to every connected system is removed too. See [People and access](/docs/people-and-access).
