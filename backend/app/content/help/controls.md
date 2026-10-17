---
title: Controls
section: Compliance
order: 20
summary: Working with controls - statuses, owners, bulk assignment, editing, custom controls, not applicable, and automation.
routes: /controls, /controls/*
---

Controls are the heart of the platform: each one is a thing your company does, mapped to every framework requirement it satisfies. See [Key concepts](/docs/concepts#controls) for the basics.

## The controls list

**Controls** lists every control in your organisation with its frameworks, owner, evidence count and health.

Filter by:

- **status** (health): Passing, Failing check, Needs evidence, In progress, Not started, Not applicable;
- **framework**: only controls mapped to that framework;
- **category**: Governance, Access control, Operations, Privacy and so on;
- **owner**: Owned by me, No owner, or anyone;
- **search**: code or title.

A control with uploads waiting for review shows "*n* awaiting review" under its health.

### Assigning owners

Every control should have an owner: the person who makes sure it works and keeps its evidence current. Owners receive reminders and the tasks created for their controls.

- **One control:** pick a person in the **Owner** column; the change saves immediately.
- **Many controls:** tick the checkboxes (or the header box for every control shown), choose a person in the bar that appears and click **Assign**. The same bar can remove owners or set a status in bulk.

New owners get an email listing what they were given. Auditors can't own controls.

## The control page

Open any control to see:

| Panel | What it shows |
| --- | --- |
| What the evidence must show | The two or three points evidence must prove, with a tick for each point covered by approved evidence |
| Evidence | Everything attached, with who added and approved it, automatic check results and the AI verdict |
| Automated checks | Results of integration checks mapped to this control, with the last run time |
| Framework requirements | Every requirement this control helps meet, by framework, with guidance |
| Implementation notes | Your description of how the control works here (auditors read this) |
| Details | Status, owner, next review date and the not-applicable reason |
| Collect automatically | Integrations that can provide evidence for this control, and whether they're connected |
| Tasks | Open and completed tasks for the control |

### Setting the status

- **Not started** and **In progress** are for your own tracking.
- **Implemented** means the control is in place. It turns **Passing** once it has current approved evidence and no failing checks.
- **Not applicable** needs a written justification first, because auditors will ask why. N/A controls are excluded from readiness.

### Editing a control

**Edit** changes the title, description, owner, category, review frequency and **what the evidence must show**. Describe controls the way they work in your company; auditors test against your description. The control code and its framework mappings never change, so your scores stay correct.

To go back to the standard evidence criteria, clear the criteria box and save.

### Review frequency

The frequency sets how long new evidence stays valid:

| Frequency | Evidence valid for |
| --- | --- |
| Continuous | 30 days (automated checks refresh it every sync) |
| Monthly | 31 days |
| Quarterly | 92 days |
| Every 6 months | 183 days |
| Yearly | 366 days |
| Once | No expiry |

Fourteen days before the last evidence expires, the platform creates a **Renew evidence** task for the owner. If an implemented control has no evidence at all, it creates an **Add evidence** task.

## Custom controls

**Add custom control** creates a control that isn't in the library, for example for an internal policy or a customer contract requirement. Give it a code (capital letters, digits and dashes, such as CUST-01), title, description, category and frequency. Custom controls work like any other but aren't mapped to framework requirements.

## Automation

A control whose evidence comes from an integration check is the most reliable kind: no one picks or edits the evidence, and it's re-checked every 6 hours. The **Collect automatically** panel shows which integrations could do this for each control. When a check fails:

1. the control's health becomes **Failing check**;
2. a **Fix:** task is created with the details and assigned to the control owner;
3. an alert goes out on your configured channels;
4. when the check passes again, the task closes and the control recovers by itself.
