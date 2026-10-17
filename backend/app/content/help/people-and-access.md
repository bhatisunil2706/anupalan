---
title: People, accounts and access reviews
section: People and training
order: 10
summary: The HR roster, matching people to their accounts, leaver checks, and quarterly access reviews routed to managers.
routes: /people, /access-reviews, /access-reviews/*
---

Several controls depend on knowing who works for you and what they can access: joiners and leavers (ACC-02, HR-05), access reviews (ACC-05) and training (HR-03). The platform brings this together from your HR system and your connected tools.

## The HR roster

**People & accounts** holds your roster: everyone who works for you, with email, name, employee ID, department, title, manager's email, status, joining date and exit date.

There are two ways to fill it:

- **Connect your HR system**: Keka, Darwinbox, greytHR or Zoho People (all in beta). The roster refreshes on every sync.
- **Upload a CSV**: export from your HR system or a spreadsheet. Only an email column is required. Column names are recognised flexibly; for example "Official Email", "DOJ", "Reporting Manager Email" and "Last Working Day" all work. Dates can be in common Indian and international formats (31-03-2026, 31/03/2026, 31 Mar 2026, 2026-03-31). A status such as "exited", "relieved", "resigned", "terminated" or "absconded", or an exit date in the past, marks a person as a leaver.

Departments from the roster drive department-based [training](/docs/training) and phishing simulations.

## Accounts

Every identity, cloud and code integration also imports the **accounts** in that system: who has an account, whether it's active, and whether it has admin rights. **People & accounts** shows each person with their accounts across systems, so you can see at a glance who has access to what.

## Leaver check

Every sync, the platform checks whether anyone who has **left** (by status or exit date) still has an **active account** in a connected system, allowing one day's grace after the exit date. If so, the automated check "Leavers have no active accounts" fails on ACC-02 and HR-05, a task is created, and the accounts are listed in a red banner at the top of **People & accounts** so you can remove them.

## Access reviews

An access review confirms that everyone with access to a system should still have it. Most frameworks expect one every quarter for important systems.

### Running a review

1. **Access reviews → Start access review**: give it a title (for example "Q3 2026 access review"), pick the systems (any connected integration with accounts) and optionally a due date (default 14 days) and a default reviewer.
2. The platform takes a snapshot of every active account in those systems and **routes each one to the person's manager** (from the HR roster). Accounts without a known manager go to the default reviewer. **Nobody reviews their own access.**
3. Reviewers get an email and decide for each account: **Keep** or **Remove**. Removing needs a short reason.
4. Each removal creates a task to remove the access. On the next sync the platform checks the account is gone, and closes the task by itself when it is.
5. When every account has a decision, an admin clicks **Complete review**. The signed-off review (CSV) is attached as evidence to **ACC-05 Periodic access reviews**, valid for 92 days.

At the start of each quarter, if no review is running, the platform creates a **Start the quarterly access review** task. Reviews can be exported to CSV at any time.
