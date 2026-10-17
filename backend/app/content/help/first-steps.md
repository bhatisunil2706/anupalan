---
title: Your first 30 days
section: Get started
order: 2
summary: A week-by-week plan from sign-up to a programme that runs itself and is ready for an auditor.
---

This plan assumes a company of 20 to 300 people starting from scratch. Smaller companies can move faster; the order stays the same.

## Day 1: set up the workspace

1. **Sign up and confirm your email.** The person who signs up becomes the **owner**.
2. **Complete onboarding.** Pick your sector; the platform suggests frameworks (for example DPDP, CERT-In, ISO 27001 and SOC 2 for B2B SaaS). Answer the short profile questions; they switch on extra requirements only when they apply, such as children's data under DPDP or card terminals under PCI DSS. You can change all of this later in **Settings**.
3. **Turn on two-step verification** for yourself under **Account security**, then require it for everyone under **Settings → Security**. Auditors will ask.
4. **Invite your admin** (the person who will run compliance day to day) and the people who own systems: engineering lead, IT, HR, finance.

## Week 1: connect your systems

Integrations do the most work for the least effort, so do them first.

1. Open **Integrations**. The **Connect next** panel lists the integrations that would automate the most controls for you.
2. Connect your identity provider first (Google Workspace, Microsoft 365 or Okta), then your cloud (AWS, Azure or Google Cloud), your code host (GitHub, GitLab or Bitbucket) and your device management tool.
3. Connect your HR system (Keka, Darwinbox, greytHR or Zoho People), or upload the HR roster as a CSV on the **People & accounts** page. This powers leaver checks, access reviews and training.
4. After the first sync, open **Controls** and filter by **Failing check**. Each failing check has a task explaining what to fix.

Every connector is read-only, except Jira, which creates issues if you ask it to. See [Integrations](/docs/integrations).

## Week 2: assign owners and write policies

1. In **Controls**, tick the controls for each area and use **Assign** to give them owners in bulk. Owners get an email.
2. In **Policies**, choose **New policy**. Upload your existing policies (Word, PDF or pasted from Google Docs), or start from the templates. Approve them; every approved policy is attached as evidence to the controls it supports, and staff are asked to acknowledge it.
3. In **Training**, check which courses are required. The three foundation courses are on by default; add role-based ones such as Secure development for Engineering.

## Week 3: fill the evidence gaps

1. Open **Controls** and filter by **Needs evidence**.
2. For each control, read **What the evidence must show** and add the evidence that shows those points. Each upload is checked automatically for common problems.
3. Someone other than the uploader reviews each item in **Evidence review**. Only approved evidence counts.
4. Mark controls that genuinely don't apply as **Not applicable**, with a reason.

## Week 4: run the operations once

1. Start your first **access review** from **Access reviews**. Managers confirm or remove each account.
2. Add your vendors in **Vendors**, set their risk tier and send each high-risk vendor a security questionnaire.
3. Fill the **Risk register** with your top ten risks and their treatment.
4. Fill the **Data inventory** (DPDP record of processing). Use **Data discovery** to find personal data in your databases.
5. Publish your consent notices and connect your website or app to the [Consent API](/docs/api#consent-api).
6. Run a **phishing simulation** to get a baseline.

## After 30 days: keep it running

The platform now tells you what needs doing:

- **Dashboard**: deadlines, controls that need attention and your tasks.
- **Tasks**: created automatically when a check fails, evidence is about to expire, a review is due or a vendor needs reassessing.
- **Alerts** by email, Slack or Teams for failing checks and legal deadlines (set up in **Settings → Notifications**).

When your readiness for a framework is above about 90%, invite your auditor with an **Auditor** account and work through the [Audit workspace](/docs/audit-workspace).
