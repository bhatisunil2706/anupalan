"""Incident timeline and email tracking.

Every significant change to an incident is written to its timeline (`incident_events`, append-only) and emailed to
the incident's followers. All emails about one incident share a thread key and a fixed subject, so they appear as a
single conversation in each follower's inbox, from the first report to closure.

Followers start as the reporter, the incident lead and the organisation's owners and admins. Anyone with access can
follow or unfollow; whoever becomes lead is added automatically.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentEvent, Membership, User
from app.regulators import CLOCKS, clocks_for
from app.services import notify

SEVERITY_LABEL = {"sev1": "SEV-1", "sev2": "SEV-2", "sev3": "SEV-3"}
STATUS_LABEL = {"open": "Open", "contained": "Contained", "resolved": "Resolved", "closed": "Closed"}
STAMPS = {
    "certin_reported_at": "Reported to CERT-In",
    "dpb_initial_reported_at": "Initial intimation sent to the Data Protection Board",
    "dpb_detailed_reported_at": "Detailed report sent to the Data Protection Board",
    "principals_notified_at": "Affected people notified",
}
# Fields whose edits are recorded on the timeline but not emailed (long-form text that changes often).
QUIET_FIELDS = {"title", "description", "category", "root_cause", "actions_taken", "lessons_learned",
                "affected_principals_estimate"}
FIELD_LABEL = {"title": "title", "description": "details", "category": "category", "root_cause": "root cause",
               "actions_taken": "actions taken", "lessons_learned": "lessons learned",
               "affected_principals_estimate": "estimate of people affected"}


def thread_key(i: Incident) -> str:
    return f"incident-{i.id}"


def label(i: Incident) -> str:
    return f"INC-{i.number}"


def org_member_ids(db: Session, org_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(Membership.user_id).where(Membership.org_id == org_id)))


def initial_followers(db: Session, i: Incident) -> list[str]:
    admins = db.scalars(select(Membership.user_id).where(Membership.org_id == i.org_id,
                                                         Membership.role.in_(("owner", "admin"))))
    ids = {*admins, *(u for u in (i.reported_by_id, i.lead_id) if u)}
    return sorted(str(u) for u in ids)


def follow(i: Incident, user_id: uuid.UUID) -> None:
    if str(user_id) not in (i.follower_ids or []):
        i.follower_ids = sorted({*(i.follower_ids or []), str(user_id)})


def unfollow(i: Incident, user_id: uuid.UUID) -> None:
    i.follower_ids = [f for f in (i.follower_ids or []) if f != str(user_id)]


def followers(db: Session, i: Incident) -> list[User]:
    """Active users who follow the incident and are still members of the organisation."""
    ids = {uuid.UUID(f) for f in (i.follower_ids or [])} & org_member_ids(db, i.org_id)
    if not ids:
        return []
    return list(db.scalars(select(User).where(User.id.in_(ids), User.is_active.is_(True)).order_by(User.full_name)))


def _recipients(db: Session, i: Incident, exclude: uuid.UUID | None) -> list[str]:
    to = [u.email for u in followers(db, i) if u.id != exclude]
    # Never let an incident go unseen: if nobody else follows it, the admins hear about it.
    return to or [e for e in notify.admin_emails(db, i.org_id)]


def _footer(i: Incident) -> str:
    return (f"\n\nYou're receiving this because you follow {label(i)}. Every update about this incident arrives in "
            "this email thread. Open the incident to post an update or to stop following it.")


def record(db: Session, i: Incident, user: User | None, kind: str, message: str, *, email: bool = True,
           headline: str | None = None, broadcast: bool = False, include_actor: bool = False) -> IncidentEvent:
    """Add a timeline entry and, unless `email` is False, email it to the followers in the incident's thread."""
    ev = IncidentEvent(org_id=i.org_id, incident_id=i.id, user_id=user.id if user else None, kind=kind,
                       message=message[:10000])
    db.add(ev)
    db.flush()
    if email:
        who = user.full_name if user else "Anupalan"
        title = headline or f"{label(i)} · {kind_label(kind)} by {who}"
        notify.queue(db, i.org_id, key=f"inc:{i.id}:ev:{ev.id}", event="incident", title=title,
                     body=message + status_line(i) + _footer(i), link=f"/incidents/{i.id}",
                     to=_recipients(db, i, None if include_actor else (user.id if user else None)),
                     broadcast=broadcast, thread=thread_key(i), subject=i.email_subject)
    return ev


def kind_label(kind: str) -> str:
    return {"reported": "Reported", "note": "Update", "status": "Status changed", "severity": "Severity changed",
            "lead": "Lead assigned", "regulatory": "Regulatory reporting", "classification": "Classification",
            "details": "Details edited", "reminder": "Deadline reminder"}.get(kind, kind.capitalize())


def status_line(i: Incident) -> str:
    parts = [f"Status: {STATUS_LABEL.get(i.status, i.status)}",
             f"Severity: {SEVERITY_LABEL.get(i.severity, i.severity)}",
             f"Lead: {i.lead.full_name if i.lead else 'not assigned'}"]
    return "\n\n" + " · ".join(parts)


def reported(db: Session, i: Incident, user: User) -> None:
    i.email_subject = f"{label(i)}: {i.title}"[:400]
    clocks = [c for c, on in (("CERT-In report within 6 hours", i.certin_reportable),
                              ("Data Protection Board detailed report within 72 hours", i.personal_data_breach)) if on]
    clocks += [f"{c.title} {c.rule[0].lower()}{c.rule[1:]}" for c in clocks_for(i.regulators)]
    lines = [f"Reported by {user.full_name}."]
    if i.description:
        lines.append(i.description[:2000])
    if clocks:
        lines.append("Clocks running: " + "; ".join(clocks) + ".")
    record(db, i, user, "reported", "\n\n".join(lines), broadcast=True, include_actor=True,
           headline=f"Incident reported: {label(i)} {i.title} ({SEVERITY_LABEL[i.severity]})")


def _fmt(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %H:%M IST")


def changes(db: Session, i: Incident, user: User, before: dict, data: dict) -> None:
    """Write timeline entries (and emails) for an update. `before` holds the old values of the changed fields."""
    if "status" in data and before["status"] != i.status:
        msg = f"Status changed from {STATUS_LABEL[before['status']]} to {STATUS_LABEL[i.status]}."
        if i.status == "closed":
            summary = [f"{k}: {getattr(i, f)}" for k, f in (("Root cause", "root_cause"),
                                                            ("Actions taken", "actions_taken"),
                                                            ("Lessons learned", "lessons_learned")) if getattr(i, f)]
            msg = f"{label(i)} was closed." + ("\n\n" + "\n\n".join(summary) if summary else "")
        record(db, i, user, "status", msg, broadcast=i.status == "closed")
    if "severity" in data and before["severity"] != i.severity:
        record(db, i, user, "severity",
               f"Severity changed from {SEVERITY_LABEL[before['severity']]} to {SEVERITY_LABEL[i.severity]}.",
               broadcast=i.severity == "sev1")
    if "lead_id" in data and before["lead_id"] != i.lead_id:
        if i.lead_id:
            follow(i, i.lead_id)
            lead = db.get(User, i.lead_id)
            record(db, i, user, "lead", f"{lead.full_name} is now the incident lead.", include_actor=False)
        else:
            record(db, i, user, "lead", "The incident lead was removed.")
    for flag, on_msg, off_msg in (
        ("certin_reportable", "Marked as reportable to CERT-In. The 6-hour reporting clock is running.",
         "No longer marked as reportable to CERT-In."),
        ("personal_data_breach", "Marked as a personal data breach. Notify affected people and the Data Protection "
                                 "Board without delay; the detailed report is due within 72 hours.",
         "No longer marked as a personal data breach."),
    ):
        if flag in data and before[flag] != getattr(i, flag):
            record(db, i, user, "classification", on_msg if getattr(i, flag) else off_msg)
    if "regulators" in data:
        added = [r for r in i.regulators or [] if r not in (before["regulators"] or [])]
        removed = [r for r in before["regulators"] or [] if r not in (i.regulators or [])]
        for r in added:
            first = next(c for c in clocks_for([r]))
            record(db, i, user, "classification",
                   f"Marked as reportable to {r.upper()}. {first.title}: {first.rule[0].lower()}{first.rule[1:]}.")
        for r in removed:
            record(db, i, user, "classification", f"No longer marked as reportable to {r.upper()}.")
    if "regulator_reported" in data:
        titles = {c.key: c.title for c in CLOCKS}
        old = before["regulator_reported"] or {}
        for key, at in data["regulator_reported"].items():
            if at is None:
                if old.get(key):
                    record(db, i, user, "regulatory", f"Cleared the recorded time for: {titles[key]}.")
            elif old.get(key) != at.isoformat():
                verb = "Time corrected: " if old.get(key) else ""
                record(db, i, user, "regulatory", f"{verb}{titles[key]} done at {_fmt(at)}.")
    for stamp, what in STAMPS.items():
        if stamp in data and getattr(i, stamp) and before[stamp] != getattr(i, stamp):
            verb = "Time corrected: " if before[stamp] else ""
            record(db, i, user, "regulatory", f"{verb}{what} at {_fmt(getattr(i, stamp))}.")
    quiet = [FIELD_LABEL[f] for f in data if f in QUIET_FIELDS and before.get(f) != getattr(i, f)]
    if quiet:
        record(db, i, user, "details", "Edited " + ", ".join(quiet) + ".", email=False)
