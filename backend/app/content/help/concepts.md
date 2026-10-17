---
title: Key concepts
section: Get started
order: 3
summary: Frameworks, requirements, controls, evidence, control health and readiness, and the rules that connect them.
---

Everything in the platform builds on a few ideas. Once you know them, the screens explain themselves.

## Frameworks and requirements

A **framework** is a law, regulation or standard: the DPDP Act, ISO 27001, SOC 2 and so on. Each framework is made of **requirements**, such as "ISO 27001 A.8.13 Information backup" or "DPDP s.8(5) Reasonable security safeguards". The platform shows each requirement with plain-language guidance. Where the source is copyrighted (ISO, AICPA, PCI SSC), the official text is not reproduced; you get the identifier and our guidance.

Some requirements only apply in certain situations; for example, DPDP's children's data rules apply only if you process children's data. These are **conditional requirements**. They switch on when you answer the matching profile question in onboarding or **Settings → Organisation**, and otherwise drop out of your scores.

## Controls

A **control** is something your company does that meets one or more requirements, for example "ACC-03 Multi-factor authentication". The platform ships a library of 110 controls, each mapped to every requirement it helps meet across all 11 frameworks. Turning on a framework adds the controls it needs that you don't already have.

Each control has:

- an **owner**: the person responsible for it;
- an **implementation status**: Not started, In progress, Implemented or Not applicable (with a written reason);
- a **review frequency**: continuous, monthly, quarterly, every 6 months, yearly or once; this sets how long evidence stays valid;
- **what the evidence must show**: two or three specific points a reviewer or auditor checks;
- **evidence** and **tasks**.

You can add your own **custom controls**, and edit the title, description, category, frequency and evidence criteria of any control.

## Evidence

**Evidence** proves a control works. It comes in five kinds:

| Kind | Example | Where it comes from |
| --- | --- | --- |
| Automated | "Root account has MFA enabled: pass" | An integration check or the evidence API |
| Policy | An approved access control policy | Approving a policy in the platform |
| File | A screenshot, PDF, export or spreadsheet | Uploaded by a person |
| Link | A Confluence page or Google Drive document | Added by a person |
| Note | "We do this by…" | Written by a person |

Every item has a **valid until** date. By default it is one review cycle from when it was added: for example 92 days for a quarterly control or 366 days for a yearly one. Evidence uploaded by people also has to be **approved by a second person** before it counts. See [Evidence](/docs/evidence).

## How control health works

Each control gets a **health** status, worked out in this order:

1. **Not applicable**: you marked it N/A with a reason. It is excluded from scores.
2. **Failing check**: any automated check mapped to it is currently failing. This wins over everything else, because a live system says the control is broken.
3. **Passing**: the control is marked Implemented and has at least one item of approved evidence that hasn't expired.
4. **Needs evidence**: the control is marked Implemented but has no current approved evidence. Evidence waiting for review shows as "awaiting review" but doesn't count yet.
5. **In progress** or **Not started**: otherwise, the control's implementation status.

## How readiness is calculated

For each framework you have turned on:

- a requirement is **met** when every control mapped to it is Passing or Not applicable;
- it is **partly met** when some of its controls are passing or in progress;
- it is **not met** otherwise;
- requirements whose condition doesn't apply to you are left out.

**Readiness %** = met requirements ÷ applicable requirements. Because controls are shared, improving one control can raise several frameworks at once.

## Tasks

A **task** is a piece of work with an assignee and due date. You can create tasks yourself, but most are created automatically:

- a check failed (the task closes itself when the check passes again);
- evidence for an implemented control is missing, or expires within 14 days;
- a policy, vendor review or quarterly access review is due;
- an access review decided an account must be removed.

## The audit trail

Every change (a status update, an upload, a download, an approval, a settings change) is written to a tamper-evident **audit log**. Each entry is chained to the previous one with a hash, so any later alteration is detectable. Admins can view and verify it in **Settings → Audit log**.
