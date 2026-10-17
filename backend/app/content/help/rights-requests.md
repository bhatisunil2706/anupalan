---
title: Rights requests and the privacy request page
section: DPDP and privacy
order: 50
summary: Receive, verify and answer data principal requests on time, including through a public request page with email verification.
routes: /dpdp/requests
---

Under the DPDP Act, people can ask you to give them information about their data, correct or erase it, nominate someone to act for them, withdraw consent, and raise grievances. **Rights requests** tracks each one from receipt to answer, with due dates.

## Request types

| Type | What the person wants |
| --- | --- |
| Access | A summary of their personal data and how it's processed |
| Correction | Inaccurate or incomplete data fixed or updated |
| Erasure | Their data deleted (unless you must keep it by law) |
| Grievance | A complaint about how their data was handled |
| Nomination | Someone to exercise their rights if they die or can't act |
| Consent withdrawal | To stop processing based on their consent |

## Due dates

Each request gets two dates:

- **Due**: the date of receipt plus your own service level, set in **Settings → Organisation** (default 30 days);
- **Legal limit**: 90 days after receipt, the most the DPDP Rules allow for responding to grievances. Your service level can never exceed it.

The assignee (or the admins, if nobody is assigned) is reminded 3 days before the due date, and again when a request becomes overdue; overdue requests are also posted to Slack or Teams. Upcoming due dates also appear on the [Dashboard](/docs/dashboard).

## Handling a request

1. **Log a rights request** (for requests by email, phone or letter): type, requester name and email, details, channel and received time, and an assignee. Requests from the public page are created automatically.
2. **Verify identity** before sharing or changing anything, then tick **Identity verified**. Ask only for what you need to confirm it's them.
3. Move the status through **New → Verifying → In progress → Completed** (or **Rejected**, with the legal reason).
4. Record the **resolution**: what you did and what you told the person. This is your evidence for PRV-10.

Use the [data inventory](/docs/data-inventory) to find where the person's data lives, and [consent records](/docs/consent-records) to see their consent history.

## The public privacy request page

DPDP expects an easy way for people to contact you. Turn on a public page in **Settings → Privacy request page**:

- set the **page address**, for example `https://app.yourcompany.com/p/your-company`;
- add your **privacy contact name and email** (your Grievance Officer or DPO), which are shown on the page;
- tick **Page is live**.

Link to it from your privacy notice, website footer and app settings. Someone filling in the form must **confirm their email address** through a link before the request is created, which filters out spam and gives you a verified contact. Submissions are rate-limited.
