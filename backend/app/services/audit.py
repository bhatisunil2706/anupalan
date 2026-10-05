from sqlalchemy.orm import Session

from app.models import AuditLog


def record(db: Session, ctx, action: str, entity=None, **detail) -> None:
    """Append an audit log entry. ctx is an OrgContext (or None for system actions)."""
    db.add(
        AuditLog(
            org_id=ctx.org_id if ctx else None,
            user_id=ctx.user.id if ctx else None,
            action=action,
            entity_type=type(entity).__name__ if entity is not None else "",
            entity_id=str(getattr(entity, "id", "")) if entity is not None else "",
            detail={k: (str(v) if not isinstance(v, (int, float, bool, type(None), list, dict)) else v)
                    for k, v in detail.items()},
        )
    )
