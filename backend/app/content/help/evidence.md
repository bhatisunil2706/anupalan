---
title: Evidence
section: Evidence and audits
order: 10
summary: The kinds of evidence, how to add it well, how long it stays valid, and the automatic checks and fingerprints that protect it.
---

Evidence is what an auditor looks at to decide whether a control works. The platform makes it easy to add, checks it automatically, has a second person approve it, and proves it hasn't been changed.

## Kinds of evidence and how much auditors trust them

Every evidence item is labelled with where it came from:

| Label | Kinds | Examples | Why it matters |
| --- | --- | --- | --- |
| **Collected automatically** | Automated | "All RDS instances are encrypted at rest: pass" | Taken straight from your systems, so no one could pick or edit it. Approved automatically. |
| **Generated in the platform** | Policy, access review, vendor assessment, training report | An approved policy; a signed-off access review | Produced by a workflow with its own approvals. Approved automatically. |
| **Uploaded** | File, link, note | A screenshot, PDF, spreadsheet, Confluence link or written note | Chosen by a person, so it's checked and needs a second person's approval. |

Automate where you can: each control's **Collect automatically** panel shows which integrations could provide its evidence.

## Adding evidence

On a control, click **Add evidence** and choose:

- **File**: PDF, PNG, JPEG, GIF, WebP, Word, Excel, PowerPoint, CSV, JSON, text, YAML or ZIP, up to 25 MB;
- **Link**: a URL to where the evidence lives (make sure the auditor will be able to open it);
- **Note**: a written statement. A note says something happens but doesn't prove it, so use it alongside a record wherever possible.

Then:

1. Give it a clear title, such as "Q3 2026 access review: AWS and GitHub".
2. Tick **This evidence shows** for each point from **What the evidence must show** that this item proves. Other evidence can cover the remaining points.
3. Optionally set **Valid until**. Otherwise it's one review cycle (see [Controls](/docs/controls#review-frequency)).

After saving you'll see the result of the automatic checks straight away. If they found a problem with the wrong file, delete it and upload the right one.

### What makes evidence good

- **Dated** within the current review period, with the date visible (in a screenshot, include the clock or a date on the page).
- **Specific**: shows your organisation's account, tenant or name.
- **Complete**: the filled-in, approved document, not the template.
- **Shows it working**, not just a rule: a policy says MFA is required; a screenshot of the identity provider's MFA enforcement setting proves it.
- **Covers every point** in What the evidence must show, across one or more items.

## What the evidence must show

Each of the 110 controls has two or three acceptance criteria, for example for ACC-03 Multi-factor authentication:

1. MFA is enforced (not just available) for all users in the identity provider.
2. MFA is enforced for cloud console and administrator access.
3. The screenshot or report shows the date or was exported within the review period.

The control page shows each point with a tick when approved evidence covers it, a dashed circle when evidence awaiting review covers it, and an empty circle when nothing covers it yet. A point counts as covered when the uploader confirms it or the AI check finds it, and a reviewer approves the evidence. Admins can change a control's criteria with **Edit**.

## Automatic checks

Every new evidence item is checked straight away. Warnings don't block anything; they tell the uploader and reviewer what to look at.

| Check | What it catches |
| --- | --- |
| Reused file | The exact same file was uploaded to this control in an earlier review period. Evidence should show the control working now. |
| Duplicate or shared file | The same file is already on this control, or on other controls (fine for a policy covering several controls). |
| Outdated document | The PDF or Office document's own date is before the review period starts. |
| Future date | The document is dated in the future. |
| Unfinished template | Placeholders such as [Company Name], [Insert date], {{name}}, TBD or lorem ipsum. |
| Very little text | A document with under 25 words. |
| Unreadable | Scanned PDFs, password-protected PDFs and old .doc/.xls files can't be read automatically; the reviewer must open them. |
| Screenshot reminder | Screenshots should show the date and the account they come from. |
| Note only | A note is a statement, not proof. |
| Broken link | Links are opened (safely) when added and re-checked weekly; "not found" and errors are flagged, and links that need a sign-in are noted so you can make sure the auditor has access. |

Click the **run checks again** icon on an item to re-run them, for example after changing a control's criteria.

If your owner has turned it on, the [AI evidence check](/docs/evidence-review#ai-evidence-check) also reads the file and gives a verdict.

## Fingerprints: proving evidence hasn't changed

When a file is uploaded, the platform calculates its **SHA-256 fingerprint**, a code that changes completely if even one byte of the file changes, before encrypting and storing it. Then:

- every download recalculates the fingerprint; if it no longer matches, the download is refused and the event is logged;
- the [evidence pack](/docs/audit-workspace#evidence-pack) records each file's upload-time fingerprint and whether the file is unchanged;
- auditor samples record the fingerprint, so a file changed after it was sampled is flagged.

Files added before fingerprints existed are fingerprinted by the background worker, marked with the date it happened.

## Expiry and renewal

Evidence counts only until its **valid until** date. When it expires, the control drops to **Needs evidence**. Fourteen days before that, the owner gets a **Renew evidence** task. Automated evidence is refreshed on every successful sync, so it doesn't expire while the integration is connected.

## Deleting evidence

Uploaded evidence can be deleted from the control page. Automated and policy evidence can't be deleted: it is managed by the integration or policy. Every deletion is recorded in the audit log.
