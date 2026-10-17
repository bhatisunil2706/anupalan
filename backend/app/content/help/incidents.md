---
title: Incidents and breaches
section: DPDP and privacy
order: 60
summary: Record security incidents and personal data breaches with live CERT-In 6-hour and DPDP Board clocks, then investigate and learn.
routes: /incidents, /incidents/*
---

When something goes wrong, the clock starts at once. **Incidents** records what happened, starts the right regulatory clocks, and keeps the whole response in one record.

## Reporting an incident

**Report an incident** and fill in:

- **Title** and **What happened**;
- **Severity**: SEV1 (critical: major outage or large breach), SEV2 (significant), SEV3 (minor);
- **Category**: for example phishing, malware, lost device, misconfiguration, unauthorised access;
- **Noticed at (IST)**: when you first became aware; all clocks run from this time;
- **Reportable to CERT-In**: tick if it's one of the incident types listed in the CERT-In Directions (for example compromise of systems, data breaches, ransomware, unauthorised access to IT systems, attacks on cloud or applications);
- **Personal data breach (DPDP)**: tick if personal data was accessed, disclosed, altered or lost without authorisation;
- **Estimated people affected** and an **Incident lead**.

Admins are alerted immediately by email (and on Slack or Teams, if connected), including which clocks are running.

## The regulatory clocks

| Clock | Starts when | Due | Reminders |
| --- | --- | --- | --- |
| CERT-In report | Reportable to CERT-In is ticked | 6 hours after the incident was noticed | 2 hours before, and when overdue |
| Data Protection Board detailed report | Personal data breach is ticked | 72 hours after the incident was noticed | 24 hours before, and when overdue |
| Notifying affected people | Personal data breach is ticked | Without delay | Shown on the dashboard until recorded |

Record each report as you make it under **Regulatory reporting**: CERT-In reported at, Board initial report at, Board detailed report at, people notified at. A clock stops when its time is recorded. The initial report to the Board is also due without delay; record when you sent it, even though it has no countdown. The dashboard shows every running clock with its countdown.

> CERT-In reports go to incident@cert-in.org.in using their reporting format; breach reports go to the Data Protection Board. The platform tracks the deadlines and keeps the record; it doesn't submit reports for you.

## Investigating and closing

Move the status through **Open → Contained → Resolved → Closed**, and fill in the **Investigation** section:

- **Root cause**: why it happened;
- **Actions taken**: containment and fixes;
- **Lessons learned**: what changes to prevent a repeat. Turn them into tasks.

A closed incident with root cause and lessons is the evidence auditors look for under INC-04 (post-incident review). Keep logs and other evidence preserved (INC-05) and attach them to the related controls.

## Practise

Run a tabletop exercise at least once a year: record a realistic scenario as an incident (mark it as an exercise in the title) and walk through the clocks. It's evidence for INC-01.
