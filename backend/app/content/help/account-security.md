---
title: Your account security
section: Administration
order: 20
summary: Two-step verification, recovery codes, password changes, signing in with SSO, and managing your signed-in devices.
routes: /account/security, /account/*
---

**Account security** (bottom of the sidebar) is where you protect your own account. A dot next to it means two-step verification is off.

## Two-step verification

Two-step verification (also called MFA or 2FA) asks for a six-digit code from an authenticator app after your password, so a stolen password alone isn't enough.

1. **Set up two-step verification** and scan the QR code with Google Authenticator, Microsoft Authenticator, 1Password, Authy or any authenticator app (or enter the key by hand).
2. Enter the six-digit code to confirm.
3. **Save your recovery codes** somewhere safe, such as a password manager. Each code works once, if you lose your phone. You can generate a new set at any time, which cancels the old ones.

Codes can't be reused, and too many wrong codes end the sign-in attempt. If your organisation requires two-step verification, you'll be asked to set it up before you can use the platform.

## Passwords

Passwords must be at least 12 characters. They're checked for strength, against your name and email, and against known data breaches. Only the first five characters of a hash of your password are sent to the breach database (Have I Been Pwned), never the password itself. Changing your password, or resetting a forgotten one, signs you out on your other devices.

After 10 failed attempts in an hour, your account is locked for an hour and you're emailed. Reset your password to get back in sooner.

## Single sign-on

If your organisation uses single sign-on (Google, Microsoft, Okta or another OIDC provider), choose **Sign in with SSO** and enter your work email. When SSO is enforced, password sign-in is turned off for everyone except owners, who keep it as break-glass access. Two-step verification is then handled by your identity provider.

## Devices and sessions

**Sessions** lists every device signed in to your account, with the browser, address and last activity. Sign out any one, or **Sign out other devices**.

Sessions end after 12 hours, or earlier after a period of inactivity that your organisation sets (2 hours by default).
