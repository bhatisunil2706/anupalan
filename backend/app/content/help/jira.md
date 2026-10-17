---
title: Jira
section: Automation
order: 20
summary: Two-way sync of compliance tasks and risks with Jira Cloud, including importing risks your team logs in Jira.
---

Many teams live in Jira. The Jira integration puts compliance work where engineers already are, and brings the status back.

## Connecting

**Integrations → Jira → Connect**:

| Field | Value |
| --- | --- |
| Jira site URL | `https://yourcompany.atlassian.net` |
| Atlassian account email | The account the API token belongs to (a service account is best) |
| API token | Create one at id.atlassian.com under Security → API tokens |
| Project key | The project for compliance issues, for example `SEC` |
| Issue type | For tasks, usually `Task` |
| Sync tasks with priority at least | `low`, `medium` (default) or `high` |
| Create a Jira issue for every new risk | `yes` (default) or `no` |
| Issue type for risks | `Task`, or `Risk` if your project has that type |
| Import risks from Jira matching this JQL | Optional, for example `project = SEC AND labels = risk` |

The account needs permission to create and edit issues in the project.

## Tasks

- Tasks at or above the chosen priority are created as Jira issues on the next sync, with a link back to the platform.
- When the issue is **Done** in Jira, the task is marked done here.
- The task shows the issue key and a link.

## Risks

- **New risks** get a Jira issue as soon as they're saved (when automatic creation is on). The issue contains the summary `[Risk] …`, the description, the score with likelihood and impact, the treatment and plan, linked controls and a link back. Labels `risk`, `anupalan` and `risk-high`, `risk-medium` or `risk-low` are added.
- **Edits** to a risk are pushed to its issue.
- **Status comes back**: when the issue's status category is **Done**, the risk becomes **Treated**; if the issue is reopened, the risk goes back to **Open**. The Jira status name is shown next to the risk.
- **Import**: issues matching your JQL that aren't already linked are imported as risks (likelihood and impact 3, treatment Mitigate; review and score them), with the assignee as owner where their email matches a member.
- If Jira is slow or down when you save a risk, the risk is still saved and the issue is created on the next sync.

On the **Risk register**, **Sync with Jira** runs a sync immediately, and **Create issue** links a risk added before Jira was connected.

## When it runs

With the other integrations, every 6 hours, and immediately when you click **Run checks** on the integration or **Sync with Jira** on the risk register.
