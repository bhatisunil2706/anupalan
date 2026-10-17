---
title: Organisation settings
section: Administration
order: 10
summary: Company details, what applies to you, the team, notifications, the privacy request page and the audit log.
routes: /settings
---

**Settings** has six tabs. Everyone can see **Organisation** and **Team**; the rest are for admins and owners.

## Organisation

- **Company**: name, sector and number of employees, plus the **rights request service level** in days (1 to 90, default 30), used for [rights request](/docs/rights-requests) due dates.
- **What applies to you**: the profile questions that switch on conditional requirements, grouped by framework and shown only for frameworks you use. See [Frameworks](/docs/frameworks#conditional-requirements-and-profile-questions). Changing an answer may add controls; the platform tells you how many.

## Team

- **Invite someone**: email, role and, for auditors, days of access. Invitations last 7 days.
- **Members**: change roles, remove people.
- **Pending invitations**: cancel an invitation that's no longer needed. To resend, cancel it and invite again.

See [Roles and permissions](/docs/roles-and-permissions).

## Security

Sign-in policy, verified domains, single sign-on, API keys, the AI assistant and evidence checks. See [Sign-in and security settings](/docs/sign-in-security).

## Notifications

The email address for organisation-wide alerts, and Slack and Teams webhooks. See [Notifications and alerts](/docs/notifications).

## Privacy request page

Turn on the public DPDP request page, set its address and the privacy contact shown on it. See [Rights requests](/docs/rights-requests#the-public-privacy-request-page).

## Audit log

Every action in the organisation, newest first: who did it, when, from which address, and the details. Each entry is chained to the previous one with a SHA-256 hash, so any change to past entries breaks the chain. **Verify integrity** checks the whole chain and shows where it breaks, if anywhere. Auditors often ask for this log, for example for changes to access or evidence.

Self-hosted operators can also verify the log from the command line with `python -m app.cli verify-audit`.
