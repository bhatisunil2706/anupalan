---
title: AI assistant
section: Automation
order: 30
summary: Draft policies, plan remediation from gaps and answer customer security questionnaires from your own documents - and what data the AI sees.
routes: /assistant
---

The AI assistant uses Claude, Anthropic's AI model, to take the first pass at writing work. It works from your own policies and controls and cites them, and people review everything before it's used.

## Turning it on

The assistant is **off by default**. The **owner** turns it on in **Settings → Security → AI assistant**, after confirming that policy and control text may be sent to the AI provider. The server needs an `ANTHROPIC_API_KEY` (see [Self-hosting](/docs/self-hosting)). Each organisation can run up to 40 assistant jobs a day.

## What it can do

### Draft a policy

Give a topic (for example "Bring your own device"), optional notes and the controls it must cover. The assistant drafts a policy in your tone, consistent with your existing policies, with sections for purpose, scope, roles, numbered policy statements, exceptions and review. Unknown facts are left as `[TODO: …]` placeholders and listed as open questions. **Save as policy** creates a draft for normal [approval](/docs/policies#approval-and-versions).

### Gap analysis and remediation plan

Pick a framework. The assistant reviews unmet requirements and your controls' states and suggests a prioritised plan: what to do first and why.

### Answer a customer's security questionnaire

Upload the customer's questionnaire (Excel or CSV with a question column), or paste questions. The assistant answers each one **from your own policies and controls**, citing the sources it used, and marks low-confidence answers where your documents don't support an answer. Edit the answers, then **export to Excel** to send back. This can turn days of work into an hour of review.

## What is sent to the AI

| Sent | Never sent |
| --- | --- |
| Your policy text, control descriptions and implementation notes | People data (roster, accounts) |
| Framework requirements and guidance | Consent records and rights requests |
| The topic, notes or questions you enter | Credentials and API keys |
| | Evidence files, unless the owner separately turns on [AI evidence checks](/docs/evidence-review#ai-evidence-check) |

## How it stays safe

- Everything retrieved from your workspace is passed as data, with an instruction never to follow instructions inside it.
- Answers must come back in a fixed format; anything else is rejected. Citations to documents that weren't sent are removed.
- Nothing is acted on automatically. Drafts become policies only when you save them, and answers go to customers only when you export them.
