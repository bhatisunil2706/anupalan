"""Notifications: queue in the database (outbox), deliver by email, Slack and Microsoft Teams from the worker.

Queueing is idempotent per (org, dedupe_key), so scheduled reminders can run repeatedly without spamming.
"""
import logging
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Membership, Notification, Organization, User
from app.security import decrypt_json, encrypt_json

log = logging.getLogger("notify")
MAX_ATTEMPTS = 5

# Only these hosts are accepted for webhooks, so a webhook can't be pointed at internal services.
SLACK_HOSTS = ("hooks.slack.com",)
TEAMS_HOST_SUFFIXES = (".webhook.office.com", ".logic.azure.com", ".environment.api.powerplatform.com")


def validate_webhook(kind: str, url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    ok = parsed.scheme == "https" and (
        host in SLACK_HOSTS if kind == "slack" else any(host.endswith(s) for s in TEAMS_HOST_SUFFIXES)
    )
    if not ok:
        expected = "https://hooks.slack.com/..." if kind == "slack" else "a Teams or Power Automate workflow URL"
        raise ValueError(f"That doesn't look like a {kind.title()} webhook. Expected {expected}")
    return url


def get_webhooks(org: Organization) -> dict:
    return decrypt_json(org.notify_webhooks_encrypted) if org.notify_webhooks_encrypted else {}


def set_webhooks(org: Organization, slack: str | None, teams: str | None) -> None:
    current = get_webhooks(org)
    if slack is not None:
        current["slack"] = validate_webhook("slack", slack)
    if teams is not None:
        current["teams"] = validate_webhook("teams", teams)
    org.notify_webhooks_encrypted = encrypt_json({k: v for k, v in current.items() if v})


def admin_emails(db: Session, org_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.org_id == org_id, Membership.role.in_(("owner", "admin")), User.is_active.is_(True))
        )
    )


def queue(
    db: Session,
    org_id: uuid.UUID,
    *,
    key: str,
    event: str,
    title: str,
    body: str = "",
    link: str = "",
    to: list[str] | None = None,
    broadcast: bool = False,
) -> None:
    """Queue a notification once per (org, key). Safe to call repeatedly."""
    stmt = (
        insert(Notification)
        .values(
            id=uuid.uuid4(), org_id=org_id, dedupe_key=key[:200], event=event, title=title[:300], body=body,
            link=link, recipients=sorted({e.lower() for e in (to or []) if e}), broadcast=broadcast,
            status="pending", attempts=0, last_error="", created_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["org_id", "dedupe_key"])
    )
    db.execute(stmt)


# ---------------------------------------------------------------- delivery


def _abs_link(link: str) -> str:
    return f"{get_settings().public_url.rstrip('/')}{link}" if link.startswith("/") else link


def send_email(to: list[str], subject: str, text: str, from_name: str | None = None) -> None:
    s = get_settings()
    if not s.smtp_host:
        log.info("email (SMTP not configured) to=%s subject=%s\n%s", to, subject, text)
        return
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, parseaddr(s.smtp_from)[1])) if from_name else s.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(text)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def send_email_safely(to: list[str], subject: str, text: str) -> None:
    """Send now, logging (not raising) on failure. Used for security emails sent from request handlers."""
    try:
        send_email(to, subject, text)
    except Exception:  # noqa: BLE001
        log.exception("failed to send email: %s", subject)


def post_slack(url: str, title: str, body: str, link: str) -> None:
    text = f"*{title}*" + (f"\n{body}" if body else "")
    if link:
        text += f"\n<{link}|Open in {get_settings().app_name}>"
    httpx.post(url, json={"text": text}, timeout=10).raise_for_status()


def post_teams(url: str, title: str, body: str, link: str) -> None:
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                    *([{"type": "TextBlock", "text": body, "wrap": True}] if body else []),
                ],
                "actions": [{"type": "Action.OpenUrl", "title": "Open", "url": link}] if link else [],
            },
        }],
    }
    httpx.post(url, json=card, timeout=10).raise_for_status()


def deliver(db: Session, n: Notification) -> None:
    org = db.get(Organization, n.org_id)
    link = _abs_link(n.link)
    errors = []
    if n.recipients and org.notify_email:
        try:
            send_email(n.recipients, f"[{org.name}] {n.title}", f"{n.body}\n\n{link}".strip())
        except Exception as e:  # noqa: BLE001 - record and retry
            errors.append(f"email: {e}")
    if n.broadcast:
        hooks = get_webhooks(org)
        for kind, fn in (("slack", post_slack), ("teams", post_teams)):
            if hooks.get(kind):
                try:
                    fn(hooks[kind], n.title, n.body, link)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{kind}: {e}")
    n.attempts += 1
    if errors:
        n.last_error = "; ".join(errors)[:1000]
        n.status = "failed" if n.attempts >= MAX_ATTEMPTS else "pending"
    else:
        n.status, n.sent_at, n.last_error = "sent", datetime.now(timezone.utc), ""


def deliver_pending(db: Session, limit: int = 100) -> int:
    rows = db.scalars(
        select(Notification).where(Notification.status == "pending").order_by(Notification.created_at).limit(limit)
    ).all()
    for n in rows:
        deliver(db, n)
        db.commit()
    return len(rows)
