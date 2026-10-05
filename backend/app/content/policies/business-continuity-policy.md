---
title: Business Continuity and Disaster Recovery Policy
slug: business-continuity-policy
controls: [BCP-01, OPS-06, OPS-07]
review_months: 12
---
# Business Continuity and Disaster Recovery Policy

**Company:** {{company}}
**Owner:** {{owner}}

## 1. Purpose

This policy makes sure {{company}} can continue critical operations and recover systems after a disruption, while keeping information secure.

## 2. Recovery objectives

| System tier | Recovery Time Objective (RTO) | Recovery Point Objective (RPO) |
| --- | --- | --- |
| Tier 1: customer-facing production | 4 hours | 1 hour |
| Tier 2: internal business systems | 24 hours | 24 hours |
| Tier 3: other systems | 72 hours | 24 hours |

## 3. Backups

1. Production data is backed up automatically, encrypted, and stored in a separate account or region within India unless otherwise approved.
2. Restores are tested at least quarterly and results are recorded.

## 4. Continuity plan

The plan covers roles and contacts, decision criteria for invoking the plan, recovery procedures for Tier 1 systems, communication with customers and regulators, and how security controls are maintained during disruption.

## 5. Testing

The plan is tested at least annually through a tabletop or failover exercise. Findings are tracked to closure.

## 6. Review

This policy is reviewed at least annually and after any invocation of the plan.
