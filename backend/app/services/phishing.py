"""Phishing simulations: realistic but harmless test emails to a company's own staff, click tracking, and a teachable
moment page. Templates use generic senders only (never real brands), emails are sent from the platform's own address
(no spoofing), targets must be on the company's own email domains, and the landing page collects nothing beyond the
click itself.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Membership, Organization, OrgDomain, PhishingCampaign, PhishingTarget, User
from app.security import hash_token, new_token
from app.services import notify
from app.services import training as tr

MAX_TARGETS = 2000

TEMPLATES: dict[str, dict] = {
    "password-expiry": {
        "name": "Password expires today", "difficulty": "Easy", "sender": "IT Helpdesk",
        "subject": "Action required: your password expires in 2 hours",
        "body": ("Hi {first_name},\n\nYour network password expires today at 5:00 PM. To avoid losing access to email "
                 "and shared drives, keep your current password by verifying your account:\n\n{link}\n\n"
                 "If you don't act, your account will be locked and you'll need to raise a ticket.\n\nIT Helpdesk"),
        "red_flags": ["Urgent deadline designed to make you rush", "Generic sender with no named person",
                      "A link to 'keep your password', which real IT teams never ask for",
                      "The sender's address isn't your company's IT system"],
    },
    "shared-document": {
        "name": "Shared document", "difficulty": "Medium", "sender": "Document Share",
        "subject": "A file was shared with you: Salary revisions FY26.xlsx",
        "body": ("Hi {first_name},\n\nA colleague at {org} shared a file with you:\n\n  Salary revisions FY26.xlsx\n"
                 "  \"Please review before tomorrow's meeting. Keep this confidential.\"\n\nOpen the file:\n{link}\n\n"
                 "This link will expire in 24 hours."),
        "red_flags": ["Curiosity bait (salary information)", "No colleague named, only 'a colleague'",
                      "Pressure to open quickly before the link 'expires'",
                      "Shared-file notifications should come from your real file-sharing tool"],
    },
    "invoice-overdue": {
        "name": "Overdue invoice", "difficulty": "Medium", "sender": "Accounts Receivable",
        "subject": "Overdue invoice INV-20931: payment required today",
        "body": ("Dear {first_name},\n\nOur records show invoice INV-20931 for Rs 1,84,500 is 15 days overdue. "
                 "To avoid a late fee and suspension of services, please review the invoice and confirm payment "
                 "today:\n\n{link}\n\nRegards,\nAccounts Receivable"),
        "red_flags": ["Threat of penalties and suspension", "An invoice you weren't expecting",
                      "No vendor name or purchase order reference",
                      "Payment requests should be checked with the vendor on a known number"],
    },
    "hr-policy": {
        "name": "HR policy acknowledgement", "difficulty": "Hard", "sender": "HR Team",
        "subject": "Updated leave and remote work policy: acknowledge by Friday",
        "body": ("Hello {first_name},\n\nWe've updated the leave and remote work policy effective next month. All "
                 "employees must read and acknowledge it by Friday.\n\nReview and acknowledge:\n{link}\n\n"
                 "Thank you,\nHR Team, {org}"),
        "red_flags": ["Looks routine, which is why it works", "Asks you to sign in through an email link",
                      "Real policy updates come through the HR system or intranet you already use",
                      "Check the sender's real address, not just the display name"],
    },
    "parcel-delivery": {
        "name": "Missed delivery", "difficulty": "Easy", "sender": "Courier Delivery",
        "subject": "Delivery attempt failed: reschedule your parcel",
        "body": ("Hi {first_name},\n\nWe tried to deliver your parcel today but no one was available. A redelivery "
                 "fee of Rs 25 applies.\n\nReschedule delivery:\n{link}\n\nParcels not rescheduled within 48 hours "
                 "are returned to sender."),
        "red_flags": ["You may not be expecting a parcel at work", "A small fee to get you to enter card details",
                      "A deadline to rush you", "No tracking number or courier name"],
    },
    "upi-refund": {
        "name": "UPI refund", "difficulty": "Medium", "sender": "Payments Team",
        "subject": "Refund of Rs 4,999 pending: confirm your UPI ID",
        "body": ("Dear {first_name},\n\nA refund of Rs 4,999 has been initiated to you but couldn't be completed. "
                 "Confirm your UPI ID to receive it within 24 hours:\n\n{link}\n\n"
                 "Note: you may be asked to enter your UPI PIN to verify."),
        "red_flags": ["You never need your UPI PIN to receive money, only to send it",
                      "A refund you weren't expecting", "Time pressure",
                      "A generic 'Payments Team' with no company named"],
    },
    "ceo-request": {
        "name": "Urgent request from leadership", "difficulty": "Hard", "sender": "Office of the CEO",
        "subject": "Quick favour, are you at your desk?",
        "body": ("Hi {first_name},\n\nI'm in back-to-back meetings and need a quick favour handled discreetly before "
                 "end of day. Please review the details here and let me know once done:\n\n{link}\n\n"
                 "Don't discuss this with others yet.\n\nSent from my phone"),
        "red_flags": ["Authority plus secrecy: 'handle discreetly', 'don't discuss'",
                      "Vague request with urgency", "Leaders don't route unusual requests through unknown links",
                      "Verify through a different channel, such as calling them"],
    },
}


def template_list() -> list[dict]:
    return [{"slug": k, "name": v["name"], "difficulty": v["difficulty"], "sender": v["sender"],
             "subject": v["subject"], "preview": v["body"].replace("{link}", "[link]").replace(
                 "{first_name}", "Asha").replace("{org}", "your company")} for k, v in TEMPLATES.items()]


def allowed_domains(db: Session, org_id: uuid.UUID) -> set[str]:
    """The company's own email domains: verified SSO domains plus the domains of its owners and admins."""
    domains = {d.domain.lower() for d in db.scalars(select(OrgDomain).where(OrgDomain.org_id == org_id))
               if getattr(d, "verified_at", None)}
    for email in db.scalars(select(User.email).join(Membership, Membership.user_id == User.id).where(
            Membership.org_id == org_id, Membership.role.in_(("owner", "admin")))):
        domains.add(email.split("@")[-1].lower())
    return domains


def eligible_targets(db: Session, org_id: uuid.UUID, departments: list[str]) -> list[tr.Learner]:
    domains = allowed_domains(db, org_id)
    return [p for p in tr.learners(db, org_id)
            if p.email.split("@")[-1] in domains and (not departments or p.department in departments)][:MAX_TARGETS]


def launch(db: Session, campaign: PhishingCampaign) -> int:
    """Create targets and send the emails. Returns the number sent."""
    org = db.get(Organization, campaign.org_id)
    tpl = TEMPLATES[campaign.template_slug]
    base = get_settings().public_url.rstrip("/")
    sent = 0
    for p in eligible_targets(db, campaign.org_id, campaign.departments or []):
        token, token_hash = new_token()
        t = PhishingTarget(org_id=campaign.org_id, campaign_id=campaign.id, email=p.email, full_name=p.full_name,
                           department=p.department, token_hash=token_hash)
        db.add(t)
        db.flush()
        first = (p.full_name or p.email).split()[0].split("@")[0].title()
        body = tpl["body"].format(first_name=first, org=org.name, link=f"{base}/l/{token}")
        try:
            notify.send_email([p.email], tpl["subject"], body, from_name=tpl["sender"])
            t.sent_at = datetime.now(timezone.utc)
            sent += 1
        except Exception as e:  # noqa: BLE001 - keep sending to everyone else
            t.send_error = str(e)[:300]
    campaign.status, campaign.sent_at = "sent", datetime.now(timezone.utc)
    return sent


def record_click(db: Session, token: str) -> PhishingTarget | None:
    t = db.scalar(select(PhishingTarget).where(PhishingTarget.token_hash == hash_token(token)))
    if not t:
        return None
    campaign = db.get(PhishingCampaign, t.campaign_id)
    if campaign.status == "closed":
        return t
    if not t.clicked_at:
        t.clicked_at = datetime.now(timezone.utc)
        if campaign.enroll_clickers:
            tr.enroll(db, t.org_id, t.email, "phishing", f"Clicked the '{campaign.name}' phishing simulation")
    return t


def results(db: Session, campaign: PhishingCampaign) -> dict:
    targets = db.scalars(select(PhishingTarget).where(PhishingTarget.campaign_id == campaign.id)
                         .order_by(PhishingTarget.email)).all()
    sent = [t for t in targets if t.sent_at]
    clicked = [t for t in sent if t.clicked_at]
    by_dept: dict[str, list[PhishingTarget]] = {}
    for t in sent:
        by_dept.setdefault(t.department or "No department", []).append(t)
    return {"sent": len(sent), "failed": len(targets) - len(sent), "clicked": len(clicked),
            "click_rate": round(100 * len(clicked) / len(sent)) if sent else 0,
            "departments": [{"department": d, "sent": len(ts), "clicked": sum(1 for t in ts if t.clicked_at),
                             "click_rate": round(100 * sum(1 for t in ts if t.clicked_at) / len(ts))}
                            for d, ts in sorted(by_dept.items())],
            "targets": [{"email": t.email, "full_name": t.full_name, "department": t.department, "sent_at": t.sent_at,
                         "clicked_at": t.clicked_at, "error": t.send_error} for t in targets]}
