from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_iccc, require_roles
from app.files import safe_filename
from app.models.event import EventObservation, EventStatus, Evidence, Observation, UrbanEvent
from app.models.user import User, UserRole
from app.schemas.common import EventOut, EventPatch, ObservationIn, ObservationOut, VerifyIn
from app.services.audit import audit
from app.services.azure_edge import StillRejected, draft_officer_brief, read_still
from app.services.dpdp import sanitize_event, sanitize_observation
from app.services.fusion import build_confirmation_ledger
from app.services.observations import ingest_observation, publish_event, save_evidence_bytes

router = APIRouter(tags=["events"])


def _sanitize_filename(filename: str) -> str:
    return safe_filename(filename)


def _event_detail(db: Session, event: UrbanEvent, user: User | None = None) -> dict:
    links = db.query(EventObservation).filter(EventObservation.event_id == event.id).all()
    obs = []
    for lnk in links:
        o = db.get(Observation, lnk.observation_id)
        if o:
            d = ObservationOut.model_validate(o).model_dump(mode="json")
            d["distance_m"] = lnk.distance_m
            obs.append(sanitize_observation(d, user))
    base = EventOut.model_validate(event).model_dump(mode="json")
    base["observations"] = obs
    return sanitize_event(base, user)


@router.post("/observations")
async def create_observation(
    body: ObservationIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_iccc),
):
    obs, event, created = ingest_observation(db, body, actor_id=user.id)
    background.add_task(publish_event, event, created)
    return {
        "observation": sanitize_observation(ObservationOut.model_validate(obs).model_dump(mode="json"), user),
        "event": sanitize_event(EventOut.model_validate(event).model_dump(mode="json"), user),
        "fused": not created,
        "created_event": created,
    }


@router.get("/observations")
def list_observations(db: Session = Depends(get_db), user: User = Depends(require_iccc), limit: int = 100):
    rows = db.query(Observation).order_by(Observation.created_at.desc()).limit(limit).all()
    return [sanitize_observation(ObservationOut.model_validate(r).model_dump(mode="json"), user) for r in rows]


@router.get("/events")
def list_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_iccc),
    status: EventStatus | None = None,
    limit: int = Query(200, le=500),
):
    q = db.query(UrbanEvent).order_by(UrbanEvent.updated_at.desc())
    if status:
        q = q.filter(UrbanEvent.status == status)
    return [sanitize_event(EventOut.model_validate(row).model_dump(mode="json"), user) for row in q.limit(limit).all()]


@router.get("/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.get(UrbanEvent, event_id) or db.query(UrbanEvent).filter(UrbanEvent.public_code == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    return _event_detail(db, event, user)


@router.get("/events/{event_id}/ledger")
def get_event_ledger(event_id: str, db: Session = Depends(get_db), user: User = Depends(require_iccc)):
    event = db.get(UrbanEvent, event_id) or db.query(UrbanEvent).filter(UrbanEvent.public_code == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    detail = _event_detail(db, event, user)
    links = db.query(EventObservation).filter(EventObservation.event_id == event.id).all()
    observations = []
    for lnk in links:
        obs = db.get(Observation, lnk.observation_id)
        if obs:
            observations.append(obs)
    ledger = build_confirmation_ledger(event, observations)
    ledger["event"] = detail
    return ledger


@router.patch("/events/{event_id}", response_model=EventOut)
def patch_event(
    event_id: str,
    body: EventPatch,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.INSPECTOR)),
):
    event = db.get(UrbanEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    if body.status:
        event.status = body.status
    if body.severity:
        event.severity = body.severity
    audit(db, "event.patch", "event", event.id, user.id, f"status={body.status} severity={body.severity}")
    db.commit()
    db.refresh(event)
    return event


@router.post("/events/{event_id}/verify")
def verify_event(
    event_id: str,
    body: VerifyIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.INSPECTOR, UserRole.ADMIN)),
):
    event = db.get(UrbanEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    event.status = EventStatus.CONFIRMED
    event.verification_count += 1
    audit(db, "event.verify", "event", event.id, user.id, body.notes)
    db.commit()
    db.refresh(event)
    background.add_task(publish_event, event, False)
    return _event_detail(db, event, user)


@router.post("/events/{event_id}/brief")
def brief_event(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    event = db.get(UrbanEvent, event_id) or db.query(UrbanEvent).filter(UrbanEvent.public_code == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    extra = dict(event.extra or {})
    drafted = draft_officer_brief(
        {
            "public_code": event.public_code,
            "event_type": event.event_type.value if event.event_type else None,
            "severity": event.severity.value if event.severity else None,
            "caption": extra.get("caption"),
            "tags": extra.get("azure_tags"),
            "fusion_reason": event.fusion_reason,
        }
    )
    extra["officer_brief"] = drafted.get("brief")
    extra["officer_brief_ai_status"] = drafted.get("ai_status")
    extra["officer_brief_model"] = drafted.get("model")
    extra["officer_brief_provider"] = drafted.get("provider")
    event.extra = extra
    audit(db, "event.brief", "event", event.id, user.id, drafted.get("ai_status"))
    db.commit()
    db.refresh(event)
    return {**_event_detail(db, event, user), "openai": drafted}


@router.post("/events/{event_id}/reject")
def reject_event(
    event_id: str,
    body: VerifyIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.INSPECTOR, UserRole.ADMIN)),
):
    event = db.get(UrbanEvent, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    event.status = EventStatus.REJECTED
    audit(db, "event.reject", "event", event.id, user.id, body.notes)
    db.commit()
    return EventOut.model_validate(event)


@router.post("/evidence/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_iccc),
):
    try:
        data = await read_still(file)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raw = file.filename or "evidence.bin"
    name = _sanitize_filename(raw)
    url = save_evidence_bytes(name, data)
    # enforce Evidence creation with DPDP flags
    ev = Evidence(url=url, restricted=True, blur_faces=True, blur_plates=True)
    db.add(ev)
    db.flush()
    audit(db, "evidence.upload", "evidence", ev.id, user.id, name)
    db.commit()
    db.refresh(ev)
    return {"url": url, "evidence_id": ev.id, "privacy": {"restricted": True, "blur_faces": True, "blur_plates": True}}
