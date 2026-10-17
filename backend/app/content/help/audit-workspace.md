---
title: Audit workspace
section: Evidence and audits
order: 30
summary: Working with your auditor - auditor accounts, evidence requests, the requirements matrix and Statement of Applicability, evidence packs and sampling.
routes: /audit
---

The **Audit workspace** is where your team and your auditor work together, instead of email threads and shared folders. Every request, comment, test and download is in the audit log.

## Give your auditor an account

In **Settings → Team**, invite the auditor with the **Auditor** role and the number of days they need (for example 60 for an audit season). They can read everything but change nothing, and their access ends automatically on that date. See [Roles and permissions](/docs/roles-and-permissions#auditor).

## Evidence requests

Auditors (and admins) raise **requests** for specific evidence:

1. **New request**: a title, description, optionally the framework requirement or control it relates to, an assignee on your team and a due date. The assignee is emailed.
2. Your team **submits** evidence: select existing evidence items, add a note and submit. Comments on the request keep the conversation in one place.
3. The auditor **accepts** the evidence or **rejects** it with a comment, and your team responds.

Filter requests by status: Open, Evidence submitted, Accepted.

## Exports

At the top of the workspace, choose a framework and download:

- the **requirements matrix** (Excel): every requirement with whether it applies (and why not, if it doesn't), its status, the controls that implement it with their implementation notes, the number of current evidence items and the control owners. For ISO 27001 this serves as your **Statement of Applicability**;
- the **evidence pack** (zip).

### Evidence pack

The evidence pack contains every current, **approved** evidence item for the framework's controls, in a folder per control:

- uploaded files, decrypted, exactly as uploaded;
- automated results, policies and notes as JSON files;
- `manifest.json` listing every file with its SHA-256 hash, who added it, who approved it and when, whether it was self-approved, automatic check warnings, the AI verdict, and for uploaded files the fingerprint taken at upload with `unchanged_since_upload`;
- `README.txt` explaining how to verify the files, and how many items were still awaiting review (those aren't included).

The manifest's own hash is written to the tamper-evident audit log when the pack is downloaded, so the pack can be verified later.

## Evidence sampling

Auditors don't check every item; they test a random **sample** in depth. **Evidence sampling** does this properly:

1. **New sample**: name it, choose a framework (or all), the period the evidence was collected in, the sample size (1 to 200) and the method:
   - **At least one per control**: one random item from each control, then random items up to the size;
   - **Simple random**: random items from the whole population.
2. The platform draws the sample from **approved** evidence only and saves the **random seed**. With the same seed and population, anyone can re-perform the selection, which auditors need to show the sample wasn't hand-picked.
3. For each item, open the file or link and record **Pass** or **Exception** (an exception needs a description). The tester and time are recorded.
4. The sample flags any item whose file **changed after it was sampled**, or was deleted.
5. **Export to Excel** gives the full working paper: population, size, seed, each item with uploader, approver, warnings, AI verdict, result, notes, tester and time.

Both auditors and admins can draw samples and record results; admins can use this for internal audits.
