"""Automation coverage (which controls run themselves, and what to connect next) and the evidence push API."""
import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.deps import DB, ApiKeyContext, Ctx, api_key_auth
from app.integrations import REGISTRY
from app.models import Control, Integration, PolicyTemplate, TestResult
from app.services import audit
from app.services.checks import record_check

router = APIRouter(tags=["automation"])

# Controls whose evidence is produced as people use a module of the app (one-click / by-product evidence).
WORKFLOWS: dict[str, str] = {
    "INC-01": "Incidents", "INC-02": "Incidents", "INC-03": "Incidents", "INC-04": "Incidents", "INC-05": "Incidents",
    "PRV-01": "Data inventory", "PRV-02": "Privacy request page", "PRV-09": "Privacy request page",
    "PRV-10": "Rights requests", "PRV-08": "Rights requests", "RISK-01": "Risk register", "RISK-02": "Risk register",
    "VEN-01": "Vendor reviews", "VEN-02": "Vendor reviews", "ACC-05": "Access reviews",
}
# Built-in checks that run without any integration once the module is used.
BUILT_IN: dict[str, list[str]] = {
    "platform.consent_capture": ["PRV-03", "PRV-04"],
    "platform.training_completion": ["HR-03"],
    "platform.leaver_access": ["ACC-02", "HR-05"],
}
FRESH_DAYS = 7


def _provider_codes() -> dict[str, set[str]]:
    return {p: {c for t in cls.tests for c in t.control_codes} for p, cls in REGISTRY.items()}


@router.get("/automation/coverage")
def coverage(db: DB, ctx: Ctx):
    controls = db.scalars(select(Control).where(Control.org_id == ctx.org_id, Control.status != "not_applicable")
                          .order_by(Control.code)).all()
    connected = {i.provider for i in db.scalars(select(Integration).where(
        Integration.org_id == ctx.org_id, Integration.status != "disabled"))}
    since = datetime.now(timezone.utc) - timedelta(days=FRESH_DAYS)
    recent: dict[str, set[str]] = {}
    for tr in db.scalars(select(TestResult).where(TestResult.org_id == ctx.org_id, TestResult.run_at >= since)):
        for code in tr.control_codes:
            recent.setdefault(code, set()).add(tr.test_key)
    policy_codes: dict[str, str] = {}
    for t in db.scalars(select(PolicyTemplate)):
        for code in t.control_codes:
            policy_codes.setdefault(code, t.title)
    by_provider = _provider_codes()

    rows, gains = [], {}
    for c in controls:
        sources, available = [], []
        for p, codes in by_provider.items():
            if c.code in codes:
                (sources if p in connected else available).append(p)
        keys = recent.get(c.code, set())
        if any(k.startswith("api.") for k in keys):
            sources.append("api")
        builtin = [k for k, codes in BUILT_IN.items() if c.code in codes and k in keys]
        if sources or builtin:
            level = "automated"
        elif c.code in WORKFLOWS or c.code in policy_codes:
            level = "assisted"
        else:
            level = "manual"
        if level != "automated":
            for p in available:
                gains.setdefault(p, []).append(c.code)
        rows.append({"id": c.id, "code": c.code, "title": c.title, "level": level,
                     "integrations": sorted(sources), "built_in": builtin, "could_automate": sorted(available),
                     "workflow": WORKFLOWS.get(c.code), "policy": policy_codes.get(c.code)})

    total = len(rows) or 1
    counts = {lvl: sum(r["level"] == lvl for r in rows) for lvl in ("automated", "assisted", "manual")}
    recs = sorted(({"provider": p, "name": REGISTRY[p].name, "category": REGISTRY[p].category,
                    "beta": REGISTRY[p].beta, "controls": sorted(codes)} for p, codes in gains.items()),
                  key=lambda r: (-len(r["controls"]), r["name"]))
    return {"total": len(rows), "counts": counts,
            "percent_automated": round(100 * counts["automated"] / total),
            "percent_hands_off": round(100 * (counts["automated"] + counts["assisted"]) / total),
            "connected": sorted(connected), "recommendations": recs[:12], "controls": rows}


# ================================================================ evidence push API

EvidenceWriter = Annotated[ApiKeyContext, Depends(api_key_auth("evidence:write"))]


class EvidenceIn(BaseModel):
    check: str = Field(description="Your stable id for this check, e.g. backup-restore-test")
    title: str = Field(min_length=3, max_length=200)
    control_codes: list[str] = Field(min_length=1, max_length=20)
    status: Literal["pass", "fail"]
    summary: str = Field(default="", max_length=2000)
    source: str = Field(default="API", max_length=100, description="Shown as the evidence source, e.g. 'Jenkins'")
    details: dict = Field(default_factory=dict)

    @field_validator("check")
    @classmethod
    def slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,80}", v):
            raise ValueError("use lowercase letters, digits, dot, dash or underscore")
        return v

    @field_validator("details")
    @classmethod
    def small(cls, v: dict) -> dict:
        import json

        if len(json.dumps(v, default=str)) > 20000:
            raise ValueError("details must be under 20 KB")
        return v


@router.post("/v1/evidence", status_code=201)
def push_evidence(body: EvidenceIn, db: DB, key: EvidenceWriter):
    """Record a check result from any tool (CI job, backup script, SIEM). Passing results become evidence on the
    controls; failing results open a task, exactly like built-in integrations."""
    known = set(db.scalars(select(Control.code).where(Control.org_id == key.org_id,
                                                      Control.code.in_(body.control_codes))))
    unknown = sorted(set(body.control_codes) - known)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown control codes: {unknown}")
    record_check(db, key.org_id, integration_id=None, source_name=body.source.strip() or "API",
                 key=f"api.{body.check}", title=body.title, control_codes=sorted(known), status=body.status,
                 summary=body.summary or body.title, details={"pushed_by": key.key.prefix, **body.details})
    audit.write(db, org_id=key.org_id, user_id=None, action="evidence.pushed", entity=None,
                detail={"check": body.check, "status": body.status, "api_key": key.key.prefix})
    db.commit()
    return {"check": f"api.{body.check}", "status": body.status, "controls": sorted(known)}
