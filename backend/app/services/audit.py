from sqlalchemy.orm import Session

from app.models.ops import AuditLog


def audit(db: Session, action: str, entity_type: str, entity_id: str, actor_id: str | None = None, detail: str = "") -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )
