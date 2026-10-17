---
title: Vendor questionnaires
section: Risk and vendors
order: 30
summary: The questionnaire library, sending core and add-on questionnaires, the vendor's experience, scoring, reminders, review and customising your own.
routes: /vendors/questionnaires, /vendors/questionnaires/*
---

A security questionnaire asks a vendor how they protect your data. The platform includes industry-standard questionnaires, sends them by secure link, scores the answers and keeps everything as evidence.

## The library

**Vendors → Questionnaires → Questionnaire library**.

### Core questionnaires: send one to every vendor

| Questionnaire | Questions | Recommended for |
| --- | ---: | --- |
| Standard security questionnaire (Full) | 96 in 18 domains | High and critical vendors |
| Standard security questionnaire (Lite) | 47 | Medium vendors |
| Quick security baseline | 26 | Low-risk vendors |

The Full questionnaire covers company and governance; policies and risk; compliance and assurance; people; assets and data; identity and access; application security; infrastructure and network; cloud; endpoints; vulnerability management; logging and monitoring; incident management; business continuity; physical security; subprocessors; privacy; and AI. Questions are referenced to ISO 27001:2022 and SOC 2, so vendors can answer from their existing audit material. The Lite set uses the same question IDs, so answers stay comparable if you later send the Full set.

These are written in-house in the structure of common industry questionnaires; they don't reproduce SIG or CAIQ. If you have a SIG licence, import it from Excel (see below).

### Add-ons: send alongside a core questionnaire when relevant

| Add-on | Questions | When |
| --- | ---: | --- |
| DPDP Data Processor | 14 | The vendor processes personal data for you (pre-selected for processors) |
| GDPR processor (Article 28) | 12 | The vendor processes personal data of people in the EU or UK |
| AI and machine learning vendor | 14 | The service uses AI on your data or supplies AI models |
| Payment card data (PCI DSS) | 9 | Payment gateways and anyone handling card data |

**View questions** shows every question with its type, expected answer, weight and references. **Excel** downloads any questionnaire.

## Sending

1. On a vendor's page, **Send questionnaire**.
2. The core questionnaire matching the vendor's tier is pre-selected; tick any add-ons. The total question count is shown.
3. Enter the vendor contact's email and the number of days until it's due (3 to 60, default 21).
4. **Send**. The vendor gets one email with a link per questionnaire. You can copy the links too.

## What the vendor sees

A secure page, no account needed, with each question grouped by section and guidance where useful. They can:

- answer Yes, No or N/A, choose from a list, or write text;
- add a comment to any answer (and must explain every N/A on a scored question);
- upload certificates and reports;
- save and come back before submitting.

Links work only until the due date and can't be guessed. Anyone with the link can answer, so send it only to the vendor's security contact.

## Tracking: Sent to vendors

**Sent to vendors** lists every questionnaire you've sent, with tiles for **Waiting for vendor**, **Ready to review**, **Expired** and **Reviewed**, search and filters. Each row shows progress (answered out of total) or the score.

- **Remind**: emails the vendor again with a **fresh link** (old links stop working) and extends the due date if it's close. You can remind at most once every 12 hours.
- **Automatic reminder**: sent 3 days before the due date if the vendor hasn't submitted.
- **Cancel**: stops the link working.
- **Download**: the answers as Excel.

## Scoring

Each yes/no question has an expected answer and a weight from 0 to 3. Weight 3 means **critical**.

- **Score** = weight of answers matching the expected answer ÷ total weight answered (N/A answers are left out), from 0 to 100.
- **Risk rating**: 85 or more is low, 65 to 84 medium, below 65 high. A wrong answer to any critical question means the rating can't be better than medium.
- Critical gaps are highlighted for the reviewer.

## Reviewing

Open a submitted questionnaire to see the score, rating, critical gaps and every answer, with answers below expectation highlighted (**Show only gaps** narrows the list). Add **review notes** (accepted risks and follow-ups) and **Mark reviewed**. The review is attached as evidence to **VEN-01 Vendor risk management**.

## Your own questionnaires

- **Duplicate to customise** any built-in questionnaire, then add, remove, reorder and edit questions.
- **New questionnaire** starts from scratch.
- **Import from Excel or CSV**: columns Section, Question, Type (Yes/No, Text or Choice), Weight (0 to 3), Expected answer, Evidence required and Options (separated by |). Only Question is required. Formulas in the file are never evaluated.

For each question set the section, type, expected answer, weight and whether to ask for evidence; choice questions need their options. Questionnaires already sent keep their own copy of the questions, so later edits never change what a vendor answered. Exports neutralise spreadsheet formulas in vendor answers, so a malicious answer can't run in Excel.
