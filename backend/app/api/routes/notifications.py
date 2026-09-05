from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.ops import NotificationLog
from app.models.user import User
from app.schemas.common import NotificationOut

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    limit: int = Query(50, le=200),
    severity: str | None = None,
):
    q = db.query(NotificationLog).order_by(NotificationLog.created_at.desc())
    if severity:
        q = q.filter(NotificationLog.severity == severity.upper())
    rows = q.limit(limit).all()
    return rows


@router.get("/notifications/count")
def notifications_count(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    severity: str | None = None,
):
    q = db.query(NotificationLog)
    if severity:
        q = q.filter(NotificationLog.severity == severity.upper())
    # count recent CRITICAL if no severity filter and caller wants critical count
    return {"count": q.count()}


@router.post("/notifications/{notif_id}/read")
def mark_read(notif_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    n = db.get(NotificationLog, notif_id)
    if not n:
        return {"ok": False}
    n.is_read = True
    db.commit()
    return {"ok": True}
