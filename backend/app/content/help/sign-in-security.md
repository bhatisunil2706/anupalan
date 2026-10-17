---
title: Sign-in and security settings
section: Administration
order: 30
summary: Require two-step verification, set session timeouts, verify domains, configure single sign-on, manage API keys and AI settings.
---

**Settings → Security** (admins) controls how people sign in and how other systems connect.

## Sign-in policy

- **Require two-step verification**: everyone must set it up before they can use the platform. The member list shows who has it, and when each person last signed in.
- **Idle timeout**: how long a session can be inactive before it ends, from 5 minutes to 24 hours (default 2 hours). Sessions always end after 12 hours.

## Verified domains

Prove you own your email domain (for example `yourcompany.com`) so single sign-on can apply to it and phishing simulations can reach it:

1. Enter the domain under **Add a domain**.
2. Add the TXT record shown (`anupalan-verification=…`) to the domain's DNS.
3. **Verify**. DNS changes can take up to an hour to appear.

## Single sign-on

The owner can connect **Google**, **Microsoft Entra ID**, **Okta** or any **OpenID Connect** provider:

1. Create an application in your identity provider, using the **redirect URI** shown in the settings.
2. Enter the client ID and secret, and for Microsoft the tenant ID, or for Okta and OIDC the domain or issuer URL.
3. **Enabled** lets people use **Sign in with SSO**.
4. **Enforced** turns off password sign-in for everyone on your verified domains except owners, who keep it for emergencies.
5. **Just-in-time provisioning** creates an account (with the default role, member or auditor) the first time someone from a verified domain signs in.

Sign-in uses the authorisation code flow with PKCE, state and nonce checks. Only verified domains are trusted.

## API keys

API keys let your own systems talk to the platform: your website sending consent records, the scanner agent, or CI jobs pushing evidence. Each key has **scopes**:

| Scope | Allows |
| --- | --- |
| `consent:write` | Record consent events from your website or app |
| `consent:read` | Read consent records and the withdrawals feed |
| `scanner:write` | Upload findings from the self-hosted personal data scanner |
| `evidence:write` | Push check results from your own tools as evidence |

The key (starting `anp_`) is shown **once**. Store it in your secrets manager. Only a hash is kept, so a lost key must be replaced. Revoke keys you no longer use; **last used** helps you find them. See the [API reference](/docs/api).

## AI assistant and evidence checks

- **AI assistant** (owner only): turns on policy drafting, gap analysis and questionnaire answering. See [AI assistant](/docs/ai-assistant).
- **Evidence checks**: second-person review of uploaded evidence (admins; on by default), and AI evidence checks (owner only; needs the assistant on). See [Evidence review](/docs/evidence-review).
