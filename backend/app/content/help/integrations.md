---
title: Integrations
section: Automation
order: 10
summary: How integrations work, connecting them safely, automation coverage, and the full catalogue of 25 integrations and their checks.
routes: /integrations
---

Integrations connect the platform to the tools you already use. They collect evidence and run checks automatically, so controls stay current without anyone uploading screenshots.

## How integrations work

1. You connect a tool with **read-only** credentials. Credentials are encrypted at rest and never shown again.
2. The platform runs the integration's **checks** straight away, then **every 6 hours**.
3. Each check maps to one or more controls:
   - **pass**: an automated evidence item is saved or refreshed on those controls, labelled "Collected automatically";
   - **fail**: the controls show **Failing check**, a **Fix:** task is created for the control owner with the details, and an alert goes to your notification channels;
   - when a failing check passes again, the task closes and the control recovers by itself.
4. Identity, cloud, code and device integrations also import **accounts** (who has access, and whether they're an admin), which power leaver checks and [access reviews](/docs/people-and-access). HR integrations import the **roster**.

Every integration is read-only except Jira, which creates issues when you ask it to.

## Connecting

**Integrations → Connect** on the tool, then fill in the fields. Each field explains where to find the value in that tool, and which read-only role or scope to grant. **Connect and run checks** verifies the credentials and runs the first sync.

On a connected integration:

- **Run checks**: sync now instead of waiting for the next scheduled run;
- **Update credentials**: rotate the key or token;
- **Disconnect**: stop syncing. Existing evidence stays until it expires.

Customer-supplied addresses (your Okta domain, Jira site, Jamf URL and so on) must be HTTPS and, in production, public. The platform refuses internal addresses to protect your network.

## Automation coverage

The **Automation coverage** panel shows, for your controls:

- how many are **fully automated** (an integration check covers them);
- how many are **one-click**: evidence is produced as a by-product of using the platform (policies, training, access reviews, vendor reviews, consent records);
- how many are **manual**: governance, HR paperwork and physical controls that need a document;
- **Connect next**: the integrations that would automate the most controls you have.

## Your own tools: the evidence API

For checks no integration covers (a backup restore test in your CI, a Jenkins job, a custom script), push results to the [evidence API](/docs/api#evidence-api) with an API key. A passing result becomes automated evidence on the controls you name; a failing one fails them.

## Catalogue

Numbers in brackets are the controls each check provides evidence for.

### Identity

| Integration | Checks |
| --- | --- |
| Google Workspace | 2-Step Verification enforced for all active users (ACC-03); all active users enrolled in 2-Step Verification (ACC-03); super admin count within limit (ACC-04); no active accounts unused for 90+ days (ACC-02, ACC-05). Imports users. |
| Microsoft 365 / Entra ID | MFA required for all users through Security defaults or Conditional Access (ACC-03); all members registered for MFA (ACC-03); Global Administrator count within limit (ACC-04). Imports users. |
| Okta | Sign-in policy requires MFA for all apps (ACC-03); all active users enrolled in MFA (ACC-03); admin count within limit (ACC-04); no dormant active accounts (ACC-05, ACC-02). Imports users. |

### Cloud

| Integration | Checks |
| --- | --- |
| Amazon Web Services | Root account MFA (ACC-03, ACC-04); IAM password policy 12+ characters (ACC-08); multi-region CloudTrail logging (LOG-01); S3 account-level public access block (NET-01, ACC-06); EBS encryption by default (CRY-01); RDS encrypted at rest (CRY-01); RDS backups kept 7+ days (OPS-06); GuardDuty enabled (LOG-02); Security Hub with a standard (OPS-04, LOG-02); Inspector scanning (OPS-02); AWS Backup plan with resources (OPS-06); CloudWatch logs kept 180+ days (LOG-01); access keys rotated within 90 days (ACC-08); production in its own account (SDL-04). Imports IAM users. |
| Microsoft Azure | Defender for Cloud Standard tier (OPS-01, LOG-02); storage enforces TLS 1.2 and blocks public blobs (NET-02, ACC-06, CRY-01); activity log exported (LOG-01); subscription Owner count within limit (ACC-04); resources hosted in Indian regions, optional (PRV-13, LOG-01). |
| Google Cloud | Project owner count within limit (ACC-04); no IAM roles for allUsers or allAuthenticatedUsers (ACC-06); buckets enforce public access prevention (ACC-06); no user-managed service account keys (ACC-08); data access audit logs on (LOG-01). |

### Source code

| Integration | Checks |
| --- | --- |
| GitHub | Organisation requires 2FA (ACC-03); default branches require pull request review (SDL-02, SDL-05); secret scanning on all repositories (ACC-08, SDL-03); Dependabot alerts on (OPS-02, SDL-03); no critical or high Dependabot alerts past the fix deadline (OPS-02, SDL-03); org admin count within limit (ACC-04, ACC-07). Imports members. |
| GitLab | Group requires 2FA (ACC-03); default branches protected, no direct developer pushes (SDL-02, SDL-05); merge requests need an approval (SDL-02); group owner count within limit (ACC-04, ACC-07). Imports members. |
| Bitbucket Cloud | Main branches require an approval and block direct pushes (SDL-02, SDL-05). |

### Devices

| Integration | Checks |
| --- | --- |
| Microsoft Intune | Devices encrypted (AST-05, CRY-01); devices compliant (AST-05, OPS-04); devices checked in within 30 days (AST-01). |
| Jamf Pro | FileVault on all Macs (AST-05, CRY-01); Macs checked in within 30 days (AST-01); supported macOS version (OPS-02, AST-05). |
| Scalefusion (beta) | Devices encrypted, compliant and checked in within 30 days. |
| Hexnode UEM (beta) | Devices encrypted, compliant and checked in within 30 days. |

### Vulnerability scanning and endpoint security

| Integration | Checks |
| --- | --- |
| Snyk | Code and dependencies are being scanned (SDL-03, OPS-02); no critical or high issues past the fix deadline (OPS-02, SDL-03). |
| Tenable Vulnerability Management | A scan completed in the last 30 days (OPS-02); no critical or high vulnerabilities past the fix deadline (OPS-02). |
| CrowdStrike Falcon | Sensors reported within 7 days (OPS-01, AST-05); no high or critical alerts open over 7 days (OPS-01, LOG-02). |
| SentinelOne | Agents active and reporting within 7 days (OPS-01, AST-05); no unresolved threats (OPS-01, LOG-02). |

Fix deadlines for vulnerabilities are configurable per integration (for example critical within 15 days, high within 30).

### Monitoring, network and IT

| Integration | Checks |
| --- | --- |
| Datadog | Log indexes keep logs for the required period, default 180 days for CERT-In (LOG-01); alert monitors exist and notify someone (LOG-02, OPS-05). |
| Cloudflare | Every site forces HTTPS with TLS 1.2+ and strict origin certificates (NET-02). |
| Freshservice | IT asset inventory updated in the last 90 days (AST-01); changes recorded through change management (SDL-05, RISK-04). |

### HR (roster import, beta)

Keka, Darwinbox, greytHR and Zoho People import employees, managers, departments, and joining and exit dates for leaver checks, access reviews and training. Field mappings should be checked against your own data the first time.

### Work tracking

Jira creates and syncs issues for tasks and risks. See [Jira](/docs/jira).

## Demo data

Demo organisations have simulated connections with sample results. They can't be synced; connect your real tools in your own organisation.
