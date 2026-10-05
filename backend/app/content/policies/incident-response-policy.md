---
title: Incident Response Policy
slug: incident-response-policy
controls: [INC-01, INC-02, INC-03, INC-04, INC-05, HR-07]
review_months: 12
---
# Incident Response Policy

**Company:** {{company}}
**Owner:** {{owner}}

## 1. Purpose

This policy defines how {{company}} detects, responds to, reports and learns from security incidents and personal data breaches.

## 2. Reporting by staff

Anyone who suspects a security incident, phishing attempt, lost device or data exposure must report it immediately to the security team through the incident channel. Do not investigate on your own or delete evidence.

## 3. Severity levels

| Level | Description | Example |
| --- | --- | --- |
| SEV-1 | Confirmed breach of personal or customer data, or major outage | Database exposed publicly |
| SEV-2 | Likely compromise with limited impact | Compromised employee account |
| SEV-3 | Suspicious event needing investigation | Phishing email reported |

## 4. Response process

1. **Triage:** decide whether the event is an incident and assign severity and an incident lead.
2. **Contain:** limit the impact (revoke credentials, isolate systems).
3. **Preserve evidence:** keep logs and system images with a record of who handled them.
4. **Eradicate and recover:** remove the cause and restore services safely.
5. **Communicate:** keep leadership, affected customers and regulators informed as required.
6. **Review:** hold a post-incident review for SEV-1 and SEV-2 incidents and track actions.

## 5. Regulatory reporting

| Authority | Trigger | Deadline |
| --- | --- | --- |
| CERT-In | Incident types listed in Annexure I of the CERT-In Directions | Within 6 hours of noticing |
| Data Protection Board | Any personal data breach | Without delay; detailed report within 72 hours |
| Affected Data Principals | Any personal data breach affecting them | Without delay |
| Sector regulator (if applicable) | As per sector rules (for example RBI, SEBI) | As per sector rules |

The incident lead records the time the incident was noticed. The platform tracks each deadline from that time. The DPO or privacy contact approves notices to Data Principals and the Board.

## 6. Testing

The incident response plan is tested at least once a year through a tabletop exercise.

## 7. Review

This policy is reviewed at least annually and after every SEV-1 incident.
