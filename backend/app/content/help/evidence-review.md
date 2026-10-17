---
title: Evidence review
section: Evidence and audits
order: 20
summary: How second-person review works, who can approve, how to review well, and the optional AI evidence check.
routes: /evidence/review
---

No software can guarantee a document is true. What auditors expect is that **someone other than the person who uploaded evidence has checked it**. The platform enforces this, and gives the reviewer automatic checks and an optional AI opinion to work with.

## How second-person review works

1. Someone uploads a file, link or note. It's marked **Awaiting review** and doesn't count yet.
2. The control's owner (or, if they uploaded it, the admins) get an email, and the item appears in **Evidence review**. The menu shows a count of items waiting for you.
3. A reviewer opens it, checks it against **What the evidence must show**, and either **approves** it or **sends it back** with a reason.
4. Approved evidence counts towards the control. Sent-back evidence never counts, and the uploader is emailed the reason.

Automated and platform-generated evidence is approved automatically.

## Who can review

- **Admins and owners** can review any evidence.
- A **control's owner** can review evidence on their controls, even as a member.
- **Nobody can approve their own upload** when someone else could. The only exception is a one-person organisation, where the uploader may approve their own evidence. That approval is labelled **Self-approved** everywhere, including the evidence pack, so the auditor knows.
- **Auditors can't review.** Their acceptance happens in the [Audit workspace](/docs/audit-workspace).

## The review queue

**Evidence review** has two tabs:

- **Waiting**: evidence awaiting review. Filter to **For me to review**, **With warnings** or **Everything waiting**. Each item shows the control, its acceptance criteria, what the uploader says it shows, the automatic check results and the AI verdict, with **Approve** and **Send back** buttons.
- **Recently reviewed**: the last 20 decisions, with who made them and when.

## How to review well

For each item, ask:

1. **Is it for this control?** A password policy isn't proof of MFA.
2. **Does it show each point** the uploader ticked, and do those points match **What the evidence must show**?
3. **Is it ours and current?** Our company or tenant name, dated in this review period.
4. **Is it complete?** A filled-in, signed document, not a template or draft.
5. **What do the warnings say?** A reused file or an old date usually means it should be sent back.

When you send something back, say exactly what's needed: "Upload this quarter's scan with the remediation status" is better than "wrong file".

## AI evidence check

When turned on, Claude (Anthropic's AI model) reads each new piece of evidence (the image, the PDF, or the text of Word, Excel and other documents) and compares it with the control's criteria. It reports:

- a verdict: **Looks right**, **Needs attention** or **Doesn't fit this control**;
- a short summary;
- for each criterion: shown, not shown or unclear, with a reason;
- specific issues, such as "placeholders are still present" or "dated before the review period";
- the organisation named in the document. If that isn't your company, the verdict becomes "Doesn't fit this control".

The verdict is **advice for the reviewer, never a decision**: it doesn't approve or reject anything. Documents can contain text written to fool an AI; the check treats file contents strictly as data, and any attempt to influence it counts against the evidence.

### Turning it on

Only the **owner** can turn it on, in **Settings → Security → Evidence checks**, and only after turning on the AI assistant. Because this sends uploaded evidence files to Anthropic's API, the owner must confirm that explicitly. Turning off the AI assistant turns evidence checks off too. The server also needs an `ANTHROPIC_API_KEY` (see [Self-hosting](/docs/self-hosting)).

Evidence checks run in the background, usually within a minute, and don't count towards the assistant's daily limit. If a check can't run, the item says so and the reviewer simply reviews it without one.

## Turning review off

Admins can turn second-person review off in **Settings → Security → Evidence checks**; new uploads then count immediately. We don't recommend it: auditors look for this separation of duties, and many standards (ISO 27001, SOC 2, PCI DSS) expect it.
