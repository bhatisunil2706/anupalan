---
title: Incidents and breaches
section: DPDP and privacy
order: 60
summary: Report incidents from the dashboard, track them by email in one thread per incident, run the CERT-In 6-hour and DPDP Board clocks, then investigate and learn.
routes: /incidents, /incidents/*
---

When something goes wrong, the clock starts at once. **Incidents** records what happened, starts the right regulatory clocks, and keeps the whole response in one record.

## Reporting an incident

Anyone in your organisation except auditors can report an incident, from two places:

- **Report incident** at the top of the **Dashboard**, so it's one click away for everyone;
- **Report incident** on the **Incidents** page.

Report as soon as you notice something, even if you're not sure it's serious: the CERT-In clock is only 6 hours. Fill in:

- **What happened** and **Details**: what you saw, which systems or data are involved, and anything you've already done. Don't paste passwords or customers' personal data;
- **Noticed at (IST)**: when you first became aware; all clocks run from this time;
- **How serious does it look?**: SEV-3 (suspicious, not sure yet), SEV-2 (likely compromise, limited impact) or SEV-1 (confirmed breach or major outage);
- **Category** (optional): for example phishing, lost device, data leak, ransomware;
- **Personal data may be involved**: tick if anyone's personal data may have been seen, copied, changed or lost. This starts the DPDP clock. If unsure, tick it; the incident lead can change it;
- **Reportable to CERT-In**: tick for incident types in the CERT-In Directions, such as unauthorised access, system compromise, data leaks, ransomware or attacks on servers and cloud accounts;
- **Incident lead** (admins only).

As soon as you report, admins are alerted by email (and on Slack or Teams, if connected), with the clocks that are running, and you get a confirmation email.

## Tracking by email

Every incident has its own **email thread**. The first email's subject is the incident number and title, for example **INC-7: Phishing email clicked**, and every later email uses the same subject and is sent as a reply. So the whole incident, from the report to closure, sits in one conversation in your inbox.

**Who gets the emails (followers):** the person who reported it, the incident lead, and your organisation's owners and admins. Whoever becomes lead is added automatically. Anyone who can see the incident can choose **Follow by email**, or **Stop email updates**, on the incident page. If nobody follows an incident, admins still get the emails.

**What's emailed:**

| Event | Example |
| --- | --- |
| Reported | Who reported it, the details and the clocks running |
| Update posted | The text of the update |
| Status changed | Open → Contained; on closing, the root cause, actions and lessons |
| Severity changed | SEV-2 → SEV-1 |
| Lead assigned | "Meera is now the incident lead." |
| Classification changed | Marked as a personal data breach or CERT-In reportable, which starts a clock |
| Regulatory report recorded | "Reported to CERT-In at 14:05 IST" |
| Deadline reminders | CERT-In 2 hours before and overdue; Board report 24 hours before and overdue |

You don't get an email about your own changes. Edits to long text, such as root cause or details, are recorded on the timeline but not emailed. Replies to these emails aren't added to the incident: post updates on the incident page so they're recorded and everyone sees them.

## Timeline and updates

The incident page shows a **Timeline** of everything that happened, newest first: the report, updates, status and severity changes, the lead, classifications, regulatory reports and edits, each with who and when. Use **Post an update** to record what you found, what you did and what happens next. Updates are emailed to followers.

The timeline can't be edited or deleted, so it's a reliable record for regulators and auditors.

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
