"""Control provisioning, control health and framework readiness."""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Control,
    ControlTemplate,
    Evidence,
    Framework,
    Mapping,
    Organization,
    OrgFramework,
    Requirement,
    TestResult,
)

FREQUENCY_DAYS = {
    "continuous": 30,
    "monthly": 31,
    "quarterly": 92,
    "semiannual": 183,
    "annual": 366,
    "once": None,
}

PROFILE_FLAGS = {
    "processes_children_data": (
        "Processes personal data of children (under 18) or persons with disability with guardians"
    ),
    "is_significant_data_fiduciary": "Notified as a Significant Data Fiduciary under DPDP",
    "uses_consent_manager": "Accepts consent through a registered DPDP Consent Manager",
    "is_infra_provider": "Provides data centre, VPS, cloud or VPN services (CERT-In subscriber records)",
    "is_virtual_asset_provider": "Virtual asset service provider, exchange or custodian wallet (CERT-In KYC records)",
    "soc2_processing_integrity": "SOC 2 report includes the Processing Integrity category",
    "soc2_privacy": "SOC 2 report includes the Privacy category",
    "eu_representative_required": "Serves people in the EU without an EU office (GDPR Art. 27 representative)",
    "pci_card_present": "Accepts card payments in person with payment terminals",
    "pci_service_provider": "Is a PCI DSS service provider (stores, processes or transmits card data for others)",
    "hipaa_clearinghouse": "Operates a healthcare clearinghouse inside a larger organisation",
}

# Which framework each profile question belongs to, so onboarding and settings only ask relevant questions.
FLAG_FRAMEWORK = {
    "processes_children_data": "dpdp", "is_significant_data_fiduciary": "dpdp", "uses_consent_manager": "dpdp",
    "is_infra_provider": "certin", "is_virtual_asset_provider": "certin",
    "soc2_processing_integrity": "soc2", "soc2_privacy": "soc2", "eu_representative_required": "gdpr",
    "pci_card_present": "pci_dss", "pci_service_provider": "pci_dss", "hipaa_clearinghouse": "hipaa",
}


def default_valid_until(frequency: str, collected: date | None = None) -> date | None:
    days = FREQUENCY_DAYS.get(frequency)
    if days is None:
        return None
    return (collected or date.today()) + timedelta(days=days)


def requirement_applies(req: Requirement, org: Organization) -> bool:
    return req.condition is None or bool((org.profile or {}).get(req.condition))


def enabled_framework_ids(db: Session, org_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(OrgFramework.framework_id).where(OrgFramework.org_id == org_id)))


def in_scope_template_ids(db: Session, org: Organization) -> set[uuid.UUID]:
    fw_ids = enabled_framework_ids(db, org.id)
    if not fw_ids:
        return set()
    rows = db.execute(
        select(Mapping.control_template_id, Requirement)
        .join(Requirement, Mapping.requirement_id == Requirement.id)
        .where(Requirement.framework_id.in_(fw_ids))
    ).all()
    return {tpl_id for tpl_id, req in rows if requirement_applies(req, org)}


def provision_controls(db: Session, org: Organization) -> int:
    """Create org controls for every in-scope template that the org does not have yet. Returns count created."""
    needed = in_scope_template_ids(db, org)
    have = set(db.scalars(select(Control.template_id).where(Control.org_id == org.id)))
    created = 0
    for tpl in db.scalars(select(ControlTemplate).where(ControlTemplate.id.in_(needed - have))):
        db.add(
            Control(
                org_id=org.id,
                template_id=tpl.id,
                code=tpl.code,
                title=tpl.title,
                description=tpl.description,
                category=tpl.category,
                frequency=tpl.frequency,
            )
        )
        created += 1
    db.flush()
    return created


# ---------------------------------------------------------------- health

HEALTH_ORDER = ["failing", "needs_evidence", "not_started", "in_progress", "passing", "not_applicable"]


@dataclass
class ControlHealth:
    health: str  # passing | failing | needs_evidence | in_progress | not_started | not_applicable
    valid_evidence: int = 0
    total_evidence: int = 0
    failing_tests: list[str] = field(default_factory=list)
    passing_tests: list[str] = field(default_factory=list)


def latest_test_results(db: Session, org_id: uuid.UUID) -> dict[str, TestResult]:
    """Latest result per test key for the org."""
    latest: dict[str, TestResult] = {}
    for tr in db.scalars(select(TestResult).where(TestResult.org_id == org_id).order_by(TestResult.run_at)):
        latest[tr.test_key] = tr
    return latest


def compute_health(
    controls: list[Control], evidence: list[Evidence], tests: dict[str, TestResult], today: date | None = None
) -> dict[uuid.UUID, ControlHealth]:
    today = today or date.today()
    ev_by_control: dict[uuid.UUID, list[Evidence]] = defaultdict(list)
    for ev in evidence:
        ev_by_control[ev.control_id].append(ev)
    tests_by_code: dict[str, list[TestResult]] = defaultdict(list)
    for tr in tests.values():
        for code in tr.control_codes:
            tests_by_code[code].append(tr)

    out = {}
    for c in controls:
        evs = ev_by_control.get(c.id, [])
        valid = [e for e in evs if e.valid_until is None or e.valid_until >= today]
        failing = [t.test_key for t in tests_by_code.get(c.code, []) if t.status in ("fail", "error")]
        passing = [t.test_key for t in tests_by_code.get(c.code, []) if t.status == "pass"]
        if c.status == "not_applicable":
            h = "not_applicable"
        elif failing:
            h = "failing"
        elif c.status == "implemented":
            h = "passing" if valid else "needs_evidence"
        else:
            h = c.status
        out[c.id] = ControlHealth(h, len(valid), len(evs), failing, passing)
    return out


def org_health(db: Session, org_id: uuid.UUID) -> tuple[list[Control], dict[uuid.UUID, ControlHealth]]:
    controls = list(
        db.scalars(
            select(Control).where(Control.org_id == org_id).options(selectinload(Control.owner)).order_by(Control.code)
        )
    )
    evidence = list(db.scalars(select(Evidence).where(Evidence.org_id == org_id)))
    return controls, compute_health(controls, evidence, latest_test_results(db, org_id))


# ---------------------------------------------------------------- readiness


def framework_readiness(db: Session, org: Organization) -> list[dict]:
    controls, health = org_health(db, org.id)
    by_template = {c.template_id: c for c in controls if c.template_id}
    results = []
    org_fws = db.scalars(
        select(OrgFramework).where(OrgFramework.org_id == org.id).options(selectinload(OrgFramework.framework))
    ).all()
    for ofw in sorted(org_fws, key=lambda o: o.framework.name):
        fw = ofw.framework
        reqs = db.scalars(
            select(Requirement)
            .where(Requirement.framework_id == fw.id)
            .options(selectinload(Requirement.mappings))
            .order_by(Requirement.order)
        ).all()
        applicable = [r for r in reqs if requirement_applies(r, org)]
        met = partial = 0
        for r in applicable:
            states = []
            for m in r.mappings:
                ctl = by_template.get(m.control_template_id)
                states.append(health[ctl.id].health if ctl else "not_started")
            ok = [s in ("passing", "not_applicable") for s in states]
            if states and all(ok):
                met += 1
            elif any(ok) or any(s in ("in_progress", "needs_evidence") for s in states):
                partial += 1
        total = len(applicable)
        results.append(
            {
                "framework_id": fw.id,
                "code": fw.code,
                "name": fw.name,
                "short_name": fw.short_name,
                "region": fw.region,
                "target_date": ofw.target_date,
                "total": total,
                "met": met,
                "partial": partial,
                "not_applicable_requirements": len(reqs) - total,
                "percent": round(100 * met / total) if total else 0,
            }
        )
    return results


def requirement_status_rows(db: Session, org: Organization, fw: Framework) -> list[dict]:
    controls, health = org_health(db, org.id)
    by_template = {c.template_id: c for c in controls if c.template_id}
    rows = []
    reqs = db.scalars(
        select(Requirement)
        .where(Requirement.framework_id == fw.id)
        .options(selectinload(Requirement.mappings))
        .order_by(Requirement.order)
    ).all()
    for r in reqs:
        applies = requirement_applies(r, org)
        linked = []
        for m in r.mappings:
            ctl = by_template.get(m.control_template_id)
            if ctl:
                linked.append({"id": ctl.id, "code": ctl.code, "title": ctl.title, "health": health[ctl.id].health})
        states = [c["health"] for c in linked]
        if not applies:
            status = "not_applicable"
        elif linked and all(s in ("passing", "not_applicable") for s in states):
            status = "met"
        elif any(s in ("passing", "not_applicable", "in_progress", "needs_evidence") for s in states):
            status = "partial"
        else:
            status = "not_met"
        rows.append(
            {
                "id": r.id,
                "ref": r.ref,
                "section": r.section,
                "title": r.title,
                "guidance": r.guidance,
                "condition": r.condition,
                "status": status,
                "controls": sorted(linked, key=lambda c: c["code"]),
            }
        )
    return rows
