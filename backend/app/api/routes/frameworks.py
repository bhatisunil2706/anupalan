from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import DB, AdminCtx, Ctx
from app.models import Framework, OrgFramework, Requirement
from app.services import audit
from app.services.compliance import framework_readiness, provision_controls, requirement_status_rows

router = APIRouter(prefix="/frameworks", tags=["frameworks"])


def _get(db, code: str) -> Framework:
    fw = db.scalar(select(Framework).where(Framework.code == code))
    if not fw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not found")
    return fw


@router.get("")
def catalog(db: DB, ctx: Ctx):
    enabled = set(db.scalars(select(OrgFramework.framework_id).where(OrgFramework.org_id == ctx.org_id)))
    counts = dict(db.execute(select(Requirement.framework_id, func.count()).group_by(Requirement.framework_id)).all())
    return [
        {"id": fw.id, "code": fw.code, "name": fw.name, "short_name": fw.short_name, "version": fw.version,
         "region": fw.region, "publisher": fw.publisher, "description": fw.description,
         "source_url": fw.source_url, "review_status": fw.review_status,
         "requirement_count": counts.get(fw.id, 0), "enabled": fw.id in enabled}
        for fw in db.scalars(select(Framework).order_by(Framework.region.desc(), Framework.name))
    ]


@router.get("/readiness")
def readiness(db: DB, ctx: Ctx):
    return framework_readiness(db, ctx.org)


@router.get("/{code}")
def detail(code: str, db: DB, ctx: Ctx):
    fw = _get(db, code)
    ofw = db.scalar(select(OrgFramework).where(OrgFramework.org_id == ctx.org_id, OrgFramework.framework_id == fw.id))
    return {
        "framework": {"id": fw.id, "code": fw.code, "name": fw.name, "short_name": fw.short_name,
                      "version": fw.version, "region": fw.region, "description": fw.description,
                      "source_url": fw.source_url, "review_status": fw.review_status,
                      "enabled": ofw is not None},
        "requirements": requirement_status_rows(db, ctx.org, fw) if ofw else [],
    }


@router.post("/{code}/enable")
def enable(code: str, db: DB, ctx: AdminCtx):
    fw = _get(db, code)
    if not db.scalar(select(OrgFramework).where(OrgFramework.org_id == ctx.org_id, OrgFramework.framework_id == fw.id)):
        db.add(OrgFramework(org_id=ctx.org_id, framework_id=fw.id))
        db.flush()
    created = provision_controls(db, ctx.org)
    audit.record(db, ctx, "framework.enabled", fw, controls_created=created)
    db.commit()
    return {"enabled": True, "controls_created": created}


@router.delete("/{code}/enable")
def disable(code: str, db: DB, ctx: AdminCtx):
    fw = _get(db, code)
    ofw = db.scalar(select(OrgFramework).where(OrgFramework.org_id == ctx.org_id, OrgFramework.framework_id == fw.id))
    if ofw:
        db.delete(ofw)
        audit.record(db, ctx, "framework.disabled", fw)
        db.commit()
    return {"enabled": False}
