---
title: Frameworks
section: Compliance
order: 10
summary: The 11 frameworks available, how to turn them on, conditional requirements, and how to read a framework's status.
routes: /frameworks, /frameworks/*
---

A framework is a law, regulation or standard you need to comply with. Turning one on adds its requirements to your readiness scores and adds any controls it needs that you don't already have.

## Available frameworks

| Framework | Region | Requirements | Who needs it |
| --- | --- | ---: | --- |
| DPDP Act 2023 + DPDP Rules 2025 | India | 49 | Every company processing digital personal data in India, or offering goods and services to people in India |
| CERT-In Directions (April 2022) | India | 7 | Service providers, intermediaries, data centres, body corporates: almost every Indian company with IT systems |
| RBI IT Governance Directions (2023) | India: sector | 26 | Banks, NBFCs (middle, upper and top layers), credit information companies; fintechs serving them via contracts |
| SEBI CSCRF (2024) | India: sector | 24 | Stock brokers, depository participants, AMCs, KRAs, RTAs, portfolio managers, AIFs, market infrastructure |
| ISO/IEC 27001:2022 | Global | 123 | Anyone selling to enterprises; the most widely recognised security certification |
| SOC 2 | Global | 61 | Companies selling to US customers; an attestation report from a CPA firm |
| NIST Cybersecurity Framework 2.0 | Global | 106 | A common language for security programmes; US customers often ask for it |
| PCI DSS v4.0.1 | Global | 63 | Anyone who stores, processes or transmits payment card data |
| ISO/IEC 42001:2023 | Global | 65 | Companies that build, provide or use AI systems |
| EU GDPR | Other regions | 43 | Companies offering services to, or monitoring, people in the EU |
| HIPAA Security and Breach Notification Rules | Other regions | 53 | Companies handling US health data for healthcare customers |

Requirement counts include conditional requirements that may not apply to you.

> **Content status.** Framework guidance is written in-house in plain language and marked "Content in review". Before relying on it for a certification, have it checked by a specialist (a lawyer for laws, a lead auditor for standards). For ISO, AICPA (SOC 2) and PCI SSC content the official text isn't reproduced; buy the standard for the full wording.

## Turning a framework on or off

Open **Frameworks**. Frameworks are grouped as India, India: sector regulators, Global standards and Other regions.

- **Turn on** adds the framework. The platform creates any controls it needs that you don't have and tells you how many were added. Existing controls, evidence and owners are reused.
- **Turn off** removes the framework from your scores. Controls and evidence stay, because other frameworks may use them.

Onboarding suggests a starting set by sector. For example, B2B SaaS gets DPDP, CERT-In, ISO 27001 and SOC 2; NBFC / lending gets DPDP, CERT-In, RBI IT Governance and ISO 27001.

## Conditional requirements and profile questions

Some requirements only apply in certain situations. They switch on when you answer the matching **profile question** in **Settings → Organisation → What applies to you** (questions are grouped by framework, and only shown for frameworks you use):

| Framework | Question | What it adds |
| --- | --- | --- |
| DPDP | Processes personal data of children or persons with disability | Verifiable parental consent, no tracking or targeted ads for children |
| DPDP | Notified as a Significant Data Fiduciary | DPO in India, independent data audits, DPIAs |
| DPDP | Accepts consent through a registered Consent Manager | Consent Manager integration |
| CERT-In | Provides data centre, VPS, cloud or VPN services | Subscriber records kept for 5 years |
| CERT-In | Virtual asset service provider | KYC and transaction records kept for 5 years |
| SOC 2 | Report includes Processing Integrity | The five PI criteria |
| SOC 2 | Report includes Privacy | The 18 Privacy criteria |
| GDPR | Serves people in the EU without an EU office | Article 27 EU representative |
| PCI DSS | Accepts card payments in person | Payment terminal protection (9.5) |
| PCI DSS | Is a PCI DSS service provider | Customer support for compliance (12.9) |
| HIPAA | Operates a healthcare clearinghouse | Isolating clearinghouse functions |

Requirements that don't apply show as **Not applicable to you** and are excluded from readiness.

## Reading a framework

Open a framework to see every requirement grouped by section, with:

- its **status**: Met, Partly met, Not met or Not applicable;
- the **guidance** in plain language;
- the **controls** mapped to it, each with its health, so you can see exactly which control is holding a requirement back.

Use the search box and status filter to find gaps quickly. Click a control to work on it.

## Exports for auditors

From the [Audit workspace](/docs/audit-workspace) you can download, for any framework:

- the **requirements matrix** as Excel; for ISO 27001 this is your **Statement of Applicability**;
- the **evidence pack**: a zip of all current approved evidence with a verification manifest.
