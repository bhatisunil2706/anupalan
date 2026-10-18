---
title: Notifications and alerts
section: Automation
order: 40
summary: The emails and Slack or Teams alerts the platform sends, and how to set up channels.
---

The platform tells people when something needs them, so nobody has to remember to check.

## Channels

Set up in **Settings → Notifications** (admins):

- **Email**: to the person concerned, and to an optional shared address (for example security@yourcompany.com) for organisation-wide alerts;
- **Slack**: an incoming webhook URL (`https://hooks.slack.com/…`);
- **Microsoft Teams**: a Teams or Power Automate workflow webhook URL.

**Send a test** checks each channel. Webhook URLs are encrypted, and only genuine Slack and Microsoft webhook addresses are accepted, so a webhook can't be pointed at an internal service.

## What gets sent

| Event | Who | When |
| --- | --- | --- |
| Check failed | Control owner or admins, plus Slack/Teams | An integration check starts failing (a Fix: task is created at the same time) |
| Incident reported | Incident followers (reporter, lead, admins), plus Slack/Teams | Immediately, with the clocks that are running |
| Incident updates | Incident followers, except whoever made the change | Updates, status, severity, lead, classification and regulatory reports, all in one email thread per incident. See [Incidents](/docs/incidents#tracking-by-email) |
| Regulatory deadlines | Incident followers, lead and admins; rights request assignee or admins | CERT-In 2 hours before and overdue; Board report 24 hours before and overdue; rights requests 3 days before and overdue |
| Task assigned or created | Assignee (or admins) | When assigned; tasks the platform creates |
| Task due | Assignee | The day before, and when overdue |
| Control assigned | New owner | When you're made owner of controls |
| Evidence to review | Control owner or admins | When someone uploads evidence |
| Evidence sent back | Uploader | With the reviewer's reason |
| Evidence request | Assignee and requester | When a request is raised, commented on, answered and decided |
| Access review | Reviewers | When accounts are assigned to you; before the due date |
| Policy approved | Everyone | When a policy needs reading and acknowledging (new members get one welcome email listing policies to read) |
| Vendor questionnaire | Vendor owner or admins | When a vendor submits, with the score |
| Vendor document expiring | Vendor owner or admins | Before and after expiry |
| Training due | Each person | At most weekly while training is overdue |

Emails link straight to the relevant page. The same event is never sent twice. Emails about one incident are threaded together in your inbox.

## Email setup

Self-hosted installations need an SMTP server (Amazon SES, Postmark, SendGrid or a Google Workspace relay) set in `SMTP_*` variables. Without one, emails are written to the worker log instead. See [Self-hosting](/docs/self-hosting).
