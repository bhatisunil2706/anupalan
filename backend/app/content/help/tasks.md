---
title: Tasks
section: Compliance
order: 40
summary: The single to-do list for compliance work, including the tasks the platform creates for you.
routes: /tasks
---

**Tasks** is where compliance work gets done. You can create tasks yourself, but most are created by the platform when something needs attention.

## Where tasks come from

| Created when | Title starts with | Closes itself? |
| --- | --- | --- |
| An integration check fails | Fix: | Yes, when the check passes again |
| An implemented control has no current evidence | Add evidence: | No; mark it done once evidence is added |
| A control's evidence expires within 14 days | Renew evidence: | No; mark it done once fresh evidence is added |
| A policy's yearly review is due | Annual review: | No; close it after re-approving |
| A vendor's review date is due | Review vendor: | No |
| A quarter starts and no access review is running | Start the quarterly access review | No |
| An access review decides to remove an account | Remove (person) from (system) | Yes, when the next sync shows the account gone |
| You create one | (your title) | No |

Tasks linked to a control appear on the control's page too.

## Working with tasks

Each task has a title, description, assignee, due date, priority (low, medium or high) and status (open, in progress or done). The list has three views: **Open**, **Assigned to me** and **Done**.

The platform never creates a duplicate: while a task of the same kind is still open for a control, vendor or policy, no second one is added.

The assignee is emailed when a task is assigned to them, the day before it is due and when it becomes overdue. Overdue tasks also show on the [Dashboard](/docs/dashboard).

## Jira

If you connect Jira, tasks at or above a chosen priority are created as Jira issues automatically, and closing the issue in Jira closes the task here. See [Jira](/docs/jira).
