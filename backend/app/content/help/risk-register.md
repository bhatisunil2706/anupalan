---
title: Risk register
section: Risk and vendors
order: 10
summary: Record, score and treat risks, link them to the controls that reduce them, and track treatment in Jira.
routes: /risks
---

A risk register lists the things that could go wrong, how likely and how bad they'd be, and what you're doing about them. ISO 27001, SOC 2, NIST CSF, HIPAA and the RBI and SEBI frameworks all require one (RISK-01, RISK-02).

## Adding a risk

**Add risk** and fill in:

| Field | Guidance |
| --- | --- |
| Risk | A specific event with a consequence: "Customer data exposed through a misconfigured storage bucket", not "Cloud security" |
| Description | Causes, affected assets and what would happen |
| Category | For example Privacy, Cloud, People, Vendor, Compliance |
| Likelihood | 1 (rare) to 5 (almost certain) |
| Impact | 1 (minor) to 5 (severe) |
| Treatment | **Mitigate** (reduce it with controls), **Accept** (live with it, approved by the owner), **Transfer** (insurance or contract) or **Avoid** (stop the activity) |
| Status | Open, Treated or Closed |
| Treatment plan | What you're doing, by when |
| Linked controls | The controls that reduce this risk |
| Owner and review date | Who's accountable, and when to look at it again |

## Scoring

**Score = likelihood × impact**, from 1 to 25:

| Score | Level |
| --- | --- |
| 15 to 25 | High |
| 8 to 14 | Medium |
| 1 to 7 | Low |

The **heat map** shows open risks by likelihood and impact; the register lists them highest first. Write down how much risk you're willing to accept (your risk appetite) and treat everything above it.

## A good first register

Start with ten to fifteen risks covering: account takeover through phishing, ransomware on laptops, cloud misconfiguration exposing data, a key vendor breach, insider misuse of customer data, missed CERT-In or DPDP deadlines, loss of a critical person, a production outage without a working backup, payment fraud through business email compromise, and vulnerable code reaching production. The demo companies include examples.

## Jira

With [Jira](/docs/jira) connected, every new risk gets a Jira issue automatically (summary, score, treatment plan and linked controls), edits are pushed to it, and the issue's status comes back: **Done** marks the risk **treated**, and reopening it sets it back to **open**. Risks your team logs in Jira can be imported too. Use **Sync with Jira** to sync straight away, or **Create issue** for a risk added before Jira was connected.

## Reviewing

Review the register at least yearly and after major changes or incidents. The review itself is evidence; note the date and decisions, and update review dates.
