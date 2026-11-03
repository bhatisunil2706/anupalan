from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DB, Ctx
from app.models import AuditLog, Incident, Policy, PolicyAcknowledgment, RightsRequest, Task, Vendor
from app.services.compliance import framework_readiness, org_health

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: DB, ctx: Ctx):
    now = datetime.now(timezone.utc)
    today = date.today()
    controls, health = org_health(db, ctx.org_id)
    counts = Counter(h.health for h in health.values())

    tasks = db.scalars(select(Task).where(Task.org_id == ctx.org_id, Task.status != "done")).all()
    my_tasks = [t for t in tasks if t.assignee_id == ctx.user.id]

    deadlines = []
    open_incidents = db.scalars(select(Incident).where(Incident.org_id == ctx.org_id, Incident.status != "closed")
                                .order_by(Incident.severity, Incident.detected_at.desc())).all()
    for i in open_incidents:
        if i.certin_due_at and not i.certin_reported_at:
            deadlines.append({"kind": "certin", "label": f"CERT-In report: INC-{i.number} {i.title}",
                              "due_at": i.certin_due_at, "link": f"/incidents/{i.id}"})
        if i.dpb_due_at and not i.dpb_detailed_reported_at:
            deadlines.append({"kind": "dpb", "label": f"Board detailed report: INC-{i.number} {i.title}",
                              "due_at": i.dpb_due_at, "link": f"/incidents/{i.id}"})
        for c in i.regulator_clocks:
            if c["due_at"] and not c["reported_at"]:
                deadlines.append({"kind": "regulator", "label": f"{c['title']}: INC-{i.number} {i.title}",
                                  "due_at": c["due_at"], "link": f"/incidents/{i.id}"})
        if i.personal_data_breach and not i.principals_notified_at:
            deadlines.append({"kind": "principals", "label": f"Notify affected users: INC-{i.number}",
                              "due_at": i.detected_at, "link": f"/incidents/{i.id}"})
    for r in db.scalars(select(RightsRequest).where(
            RightsRequest.org_id == ctx.org_id, RightsRequest.status.not_in(("completed", "rejected")))):
        deadlines.append({"kind": "request", "label": f"DPR-{r.number}: {r.request_type.replace('_', ' ')} from "
                                                      f"{r.requester_name}", "due_at": r.due_at,
                          "link": "/dpdp/requests"})
    for t in tasks:
        if t.due_date and t.due_date <= today + timedelta(days=7):
            deadlines.append({"kind": "task", "label": t.title,
                              "due_at": datetime.combine(t.due_date, datetime.min.time(), tzinfo=timezone.utc),
                              "link": "/tasks"})
    deadlines.sort(key=lambda d: d["due_at"])

    approved = db.scalars(select(Policy).where(Policy.org_id == ctx.org_id, Policy.status == "approved")).all()
    acked = {(a.policy_id, a.version) for a in db.scalars(
        select(PolicyAcknowledgment).where(PolicyAcknowledgment.user_id == ctx.user.id,
                                           PolicyAcknowledgment.org_id == ctx.org_id))}
    to_ack = [{"id": p.id, "title": p.title, "version": p.version} for p in approved
              if (p.id, p.version) not in acked]

    vendors_due = db.scalars(select(Vendor).where(
        Vendor.org_id == ctx.org_id, Vendor.status != "offboarded", Vendor.next_review_date.is_not(None),
        Vendor.next_review_date <= today + timedelta(days=30))).all()

    activity = db.scalars(select(AuditLog).where(AuditLog.org_id == ctx.org_id).order_by(AuditLog.at.desc())
                          .limit(12)).all()

    attention = sorted(
        (c for c in controls if health[c.id].health in ("failing", "needs_evidence")),
        key=lambda c: (health[c.id].health != "failing", c.code),
    )[:8]

    return {
        "readiness": framework_readiness(db, ctx.org),
        "control_counts": {k: counts.get(k, 0) for k in
                           ("passing", "failing", "needs_evidence", "in_progress", "not_started", "not_applicable")},
        "total_controls": len(controls),
        "attention": [{"id": c.id, "code": c.code, "title": c.title, "health": health[c.id].health} for c in attention],
        "open_tasks": len(tasks),
        "overdue_tasks": sum(1 for t in tasks if t.due_date and t.due_date < today),
        "my_tasks": [{"id": t.id, "title": t.title, "due_date": t.due_date, "priority": t.priority}
                     for t in sorted(my_tasks, key=lambda t: (t.due_date is None, t.due_date))[:6]],
        "deadlines": [{**d, "overdue": d["due_at"] < now} for d in deadlines[:10]],
        "open_incidents": [{"id": i.id, "number": i.number, "title": i.title, "severity": i.severity,
                            "status": i.status, "detected_at": i.detected_at} for i in open_incidents[:6]],
        "policies_to_acknowledge": to_ack,
        "vendor_reviews_due": [{"id": v.id, "name": v.name, "next_review_date": v.next_review_date}
                               for v in vendors_due],
        "activity": [{"at": a.at, "action": a.action, "user": a.user.full_name if a.user else "System",
                      "detail": a.detail} for a in activity],
    }
