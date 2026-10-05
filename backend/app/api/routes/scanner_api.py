"""Machine API for the self-hosted scanner agent, which runs inside the customer's network."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.deps import DB, ApiKeyContext, api_key_auth
from app.models import DataSource, PiiFinding
from app.services import audit
from app.services.pii import LABELS, mask

router = APIRouter(tags=["discovery"])
ScannerKey = Annotated[ApiKeyContext, Depends(api_key_auth("scanner:write"))]


class AgentFinding(BaseModel):
    container: str = Field(max_length=500)
    field: str = Field(default="", max_length=300)
    category: str
    matches: int = Field(default=0, ge=0)
    sampled: int = Field(default=0, ge=0)
    by_name_only: bool = False
    examples: list[str] = Field(default_factory=list, max_length=3)


class AgentReport(BaseModel):
    source_name: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(default="postgres", pattern="^(postgres|mysql|s3)$")
    agent_version: str = Field(default="", max_length=40)
    stats: dict[str, int] = Field(default_factory=dict)
    findings: list[AgentFinding] = Field(default_factory=list, max_length=20000)


@router.post("/v1/scanner/findings")
def report(body: AgentReport, db: DB, key: ScannerKey):
    s = db.scalar(select(DataSource).where(DataSource.org_id == key.org_id, DataSource.kind == "agent",
                                           DataSource.name == body.source_name))
    if not s:
        s = DataSource(org_id=key.org_id, name=body.source_name, kind="agent", config={})
        db.add(s)
        db.flush()
    now = datetime.now(timezone.utc)
    s.config = {"engine": body.source_kind, "agent_version": body.agent_version, "api_key": key.key.prefix}
    db.execute(delete(PiiFinding).where(PiiFinding.source_id == s.id))
    kept = 0
    for f in body.findings:
        if f.category not in LABELS:
            continue
        # Never trust the agent to have masked correctly: mask again (idempotent on masked values).
        examples = [mask(f.category, e[:200]) for e in f.examples if e.strip()]
        db.add(PiiFinding(org_id=key.org_id, source_id=s.id, container=f.container, field=f.field,
                          category=f.category, matches=f.matches, sampled=f.sampled, by_name_only=f.by_name_only,
                          examples=examples, scanned_at=now))
        kept += 1
    s.status, s.last_error, s.last_scan_at = "scanned", "", now
    s.stats = {**{k: int(v) for k, v in list(body.stats.items())[:10]}, "findings": kept}
    audit.write(db, org_id=key.org_id, user_id=None, action="data_source.agent_report", entity=s,
                detail={"findings": kept, "api_key": key.key.prefix})
    db.commit()
    return {"source_id": s.id, "findings": kept}
