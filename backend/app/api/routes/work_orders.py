from datetime import datetime, timezone

import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.event import EventStatus, UrbanEvent
from app.models.user import User, UserRole
from app.models.work_order import Repair, WorkOrder, WorkOrderStatus
from app.schemas.common import RepairIn, VerifyRepairIn, WorkOrderIn, WorkOrderPatch
from app.persist import write_extra
from app.services.audit import audit
from app.services.observations import publish_event

router = APIRouter(tags=["work-orders"])

_CODE_RE = re.compile(r"^WO-(\d+)$")
_CODE_ATTEMPTS = 5
# Only POST /work-orders/{id}/verify may close or fail a work order, because it also moves the event and publishes.
_VERIFY_ONLY = {WorkOrderStatus.RESOLVED, WorkOrderStatus.FAILED}


def _find_wo(db: Session, wo_id: str) -> WorkOrder | None:
    """UUID or public code (WO-001), the same lookup for every route."""
    return db.get(WorkOrder, wo_id) or db.query(WorkOrder).filter(WorkOrder.public_code == wo_id).first()


def _next_code(db: Session) -> str:
    """One past the highest existing WO-NNN. count()+1 repeats a live code after any delete."""
    top = db.scalar(
        select(WorkOrder.public_code)
        .where(WorkOrder.public_code.like("WO-%"))
        .order_by(func.length(WorkOrder.public_code).desc(), WorkOrder.public_code.desc())
        .limit(1)
    )
    match = _CODE_RE.match(top or "")
    return f"WO-{(int(match.group(1)) if match else 0) + 1:03d}"


def _out(wo: WorkOrder) -> dict:
    ev = wo.event
    extra = (ev.extra or {}) if ev else {}
    return {
        "id": wo.id,
        "public_code": wo.public_code,
        "event_id": wo.event_id,
        "asset_id": wo.asset_id,
        "title": wo.title,
        "description": wo.description,
        "status": wo.status.value,
        "assignee_id": wo.assignee_id,
        "qr_payload": wo.qr_payload,
        "repair_notes": wo.repair_notes,
        "repair_evidence_url": wo.repair_evidence_url,
        "verify_notes": wo.verify_notes,
        "created_at": wo.created_at,
        "updated_at": wo.updated_at,
        "event_code": ev.public_code if ev else None,
        "event_type": ev.event_type.value if ev else None,
        "event_severity": ev.severity.value if ev else None,
        "latitude": ev.latitude if ev else None,
        "longitude": ev.longitude if ev else None,
        "observation_count": ev.observation_count if ev else None,
        "source_count": ev.source_count if ev else None,
        "confidence": ev.confidence if ev else None,
        "simulated": ev.simulated if ev else None,
        "ai_status": extra.get("ai_status"),
    }


@router.get("/work-orders")
def list_wo(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_out(w) for w in db.query(WorkOrder).options(joinedload(WorkOrder.event)).order_by(WorkOrder.created_at.desc()).all()]


@router.post("/work-orders")
def create_wo(
    body: WorkOrderIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.INSPECTOR)),
):
    # Two creates can read the same max; the unique public_code/qr_payload makes the loser retry.
    for _ in range(_CODE_ATTEMPTS):
        code = _next_code(db)
        wo = WorkOrder(
            public_code=code,
            event_id=body.event_id,
            asset_id=body.asset_id,
            title=body.title,
            description=body.description,
            assignee_id=body.assignee_id,
            status=WorkOrderStatus.ASSIGNED if body.assignee_id else WorkOrderStatus.PENDING,
            qr_payload=f"urbansense://work-order/{code}",
        )
        try:
            with db.begin_nested():
                db.add(wo)
        except IntegrityError as exc:
            detail = str(exc.orig)
            if "public_code" in detail or "qr_payload" in detail:
                continue
            raise HTTPException(400, "Work order references an unknown event, asset or assignee") from exc
        break
    else:
        raise HTTPException(503, "Could not allocate a work order code. Retry.")
    if body.event_id:
        ev = db.get(UrbanEvent, body.event_id)
        if ev:
            ev.status = EventStatus.ASSIGNED
            background.add_task(publish_event, ev, False)
    audit(db, "work_order.create", "work_order", code, user.id)
    db.commit()
    db.refresh(wo)
    return _out(wo)


@router.get("/work-orders/{wo_id}")
def get_wo(wo_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    wo = _find_wo(db, wo_id)
    if not wo:
        raise HTTPException(404, "Work order not found")
    return _out(wo)


@router.patch("/work-orders/{wo_id}")
def patch_wo(
    wo_id: str,
    body: WorkOrderPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.INSPECTOR)),
):
    wo = _find_wo(db, wo_id)
    if not wo:
        raise HTTPException(404, "Work order not found")
    if body.status in _VERIFY_ONLY:
        raise HTTPException(400, f"Use POST /work-orders/{wo.public_code}/verify to set {body.status.value}")
    if body.status:
        wo.status = body.status
    if body.assignee_id:
        wo.assignee_id = body.assignee_id
        if wo.status == WorkOrderStatus.PENDING:
            wo.status = WorkOrderStatus.ASSIGNED
    if body.title:
        wo.title = body.title
    audit(db, "work_order.patch", "work_order", wo.id, user.id)
    db.commit()
    return _out(wo)


@router.post("/work-orders/{wo_id}/repair")
def submit_repair(
    wo_id: str,
    body: RepairIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.INSPECTOR, UserRole.ADMIN)),
):
    wo = _find_wo(db, wo_id)
    if not wo:
        raise HTTPException(404, "Work order not found")
    wo.repair_notes = body.notes
    wo.repair_evidence_url = body.evidence_url
    wo.status = WorkOrderStatus.RE_VERIFICATION
    db.add(Repair(work_order_id=wo.id, notes=body.notes, evidence_url=body.evidence_url, result="SUBMITTED"))
    if wo.event_id:
        ev = db.get(UrbanEvent, wo.event_id)
        if ev:
            ev.status = EventStatus.RE_VERIFICATION
            extra = dict(ev.extra or {})
            extra["repair_passes"] = []
            extra["repair_opened_at"] = datetime.now(timezone.utc).isoformat()
            write_extra(ev, extra)
            background.add_task(publish_event, ev, False)
    audit(db, "work_order.repair", "work_order", wo.id, user.id, body.notes)
    db.commit()
    return _out(wo)


@router.post("/work-orders/{wo_id}/verify")
def verify_repair(
    wo_id: str,
    body: VerifyRepairIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.INSPECTOR, UserRole.ADMIN)),
):
    wo = _find_wo(db, wo_id)
    if not wo:
        raise HTTPException(404, "Work order not found")
    wo.verify_notes = body.notes
    if body.passed:
        wo.status = WorkOrderStatus.RESOLVED
        if wo.event_id:
            ev = db.get(UrbanEvent, wo.event_id)
            if ev:
                ev.status = EventStatus.RESOLVED
                background.add_task(publish_event, ev, False)
    else:
        wo.status = WorkOrderStatus.FAILED
        if wo.event_id:
            ev = db.get(UrbanEvent, wo.event_id)
            if ev:
                ev.status = EventStatus.REOPENED
                background.add_task(publish_event, ev, False)
    audit(db, "work_order.verify", "work_order", wo.id, user.id, f"passed={body.passed} {body.notes}")
    db.commit()
    return _out(wo)
