---
title: Roles and permissions
section: Get started
order: 4
summary: What owners, admins, members and auditors can see and do, and how to invite and manage people.
---

Every person in an organisation has one of four roles. A person can belong to several organisations (for example a consultant or group company) and switch between them from the organisation menu at the top of the sidebar.

## The four roles

| | Owner | Admin | Member | Auditor |
| --- | :---: | :---: | :---: | :---: |
| See everything in the workspace | ✓ | ✓ | ✓ | ✓ (read-only) |
| Update controls, upload evidence, manage tasks, risks, vendors, DPDP records | ✓ | ✓ | ✓ | |
| Own controls and policies | ✓ | ✓ | ✓ | |
| Review (approve or send back) uploaded evidence | ✓ | ✓ | Only for controls they own | |
| Approve and delete policies | ✓ | ✓ | | |
| Invite people, change roles, remove members | ✓ | ✓ | | |
| Connect integrations, manage settings, notifications and API keys | ✓ | ✓ | | |
| Manage training assignments, company courses and phishing simulations | ✓ | ✓ | | |
| Raise evidence requests, accept or reject submitted evidence | ✓ | ✓ | | ✓ |
| Draw evidence samples and record test results | ✓ | ✓ | | ✓ |
| Download the evidence pack and requirements matrix | ✓ | ✓ | | ✓ |
| Turn the AI assistant and AI evidence checks on or off | ✓ | | | |
| Configure single sign-on | ✓ | | | |

Nobody can approve evidence they uploaded themselves while someone else is able to; see [Evidence review](/docs/evidence-review).

## Owner

The person who creates the organisation is its owner. Owners have every admin right plus a few decisions that affect data sharing or sign-in for everyone: the AI assistant, AI evidence checks and single sign-on. When single sign-on is enforced, owners can still sign in with their password and two-step verification as break-glass access.

## Admin

Admins run the compliance programme. Most organisations have one or two.

## Member

Members do the day-to-day work: they own controls, add evidence, complete tasks and training, and handle DPDP requests and incidents. Use the member role for anyone who isn't running the programme.

## Auditor

The auditor role is for external auditors and assessors. Auditors:

- can see every control, policy, piece of evidence and record, but can't change any of them;
- have **time-limited access**: you choose how many days (1 to 365) when you invite them, and access ends automatically; a banner shows them the end date;
- work in the [Audit workspace](/docs/audit-workspace): they raise evidence requests, accept or reject what your team submits, test samples, and download exports;
- can't own controls or policies, and can't review evidence.

## Inviting people

**Settings → Team → Invite someone.** Enter the email address and role. For auditors, also set the number of days of access. The invitation link is valid for 7 days. You must have confirmed your own email address before you can invite others.

People from your HR roster who don't have an account can be invited in one go from **Training → Team progress → Invite them**, so they can take their training.

## Changing or removing access

In **Settings → Team**, change a member's role or remove them. Removing someone takes away their access to the organisation straight away. Their past work (evidence, approvals, audit log entries) keeps their name.

If you use single sign-on with just-in-time provisioning, new people from your verified domains get an account with the default role (member or auditor) the first time they sign in. See [Sign-in and security settings](/docs/sign-in-security).
