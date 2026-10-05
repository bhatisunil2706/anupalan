---
title: Access Control Policy
slug: access-control-policy
controls: [ACC-01, ACC-02, ACC-03, ACC-04, ACC-05, ACC-06, ACC-08]
review_months: 12
---
# Access Control Policy

**Company:** {{company}}
**Owner:** {{owner}}

## 1. Purpose

This policy makes sure that only authorised people have access to {{company}} systems and data, and only the access they need.

## 2. Principles

- **Least privilege:** grant the minimum access needed for the role.
- **Need to know:** access to personal data and confidential data is limited to roles that require it.
- **Unique accounts:** every person has their own account. Shared accounts are not allowed except documented service accounts.

## 3. Account lifecycle

1. **Joiners:** access is granted on an approved request from the manager, based on role.
2. **Movers:** access is reviewed and adjusted within 5 working days of a role change.
3. **Leavers:** all access is removed within 24 hours of exit. Devices are recovered.

## 4. Authentication

1. Multi-factor authentication is mandatory for the identity provider, email, cloud consoles, source code hosting, and all administrative or remote access.
2. Passwords are at least 12 characters, not reused, and stored in the company password manager.
3. Secrets, API keys and credentials are never stored in source code. Repositories are scanned for leaked secrets.

## 5. Privileged access

1. Administrative access is limited to named individuals approved by the security lead.
2. Cloud root accounts are protected with hardware or app-based MFA and used only for break-glass tasks.
3. Privileged activity is logged.

## 6. Access reviews

Access to critical systems (cloud, production databases, identity provider, source code, systems holding personal data) is reviewed every quarter by system owners. Unneeded access is removed and the review is recorded.

## 7. Review

This policy is reviewed at least annually.
