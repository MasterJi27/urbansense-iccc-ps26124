"""Citizen QR report — no ICCC login. Own-ticket via HMAC claim, not a shared inbox."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.event import EventType, Severity, SourceType, UrbanEvent
from app.models.ops import NotificationLog
from app.schemas.common import CitizenReportIn, ObservationIn
from app.services.citizen_claims import merge_citizen_claim, read_citizen_claim
from app.services.extras import sanitize_extra
from app.services.departments import department_for
from app.services.dpdp import mask_contact, sanitize_event
from app.services.observations import ingest_observation
from app.services.rate_limit import client_ip, enforce

router = APIRouter(tags=["citizen"])


@router.post("/citizen/report")
def citizen_report(body: CitizenReportIn, request: Request, db: Session = Depends(get_db)):
    enforce(f"citizen:{client_ip(request)}", limit=12, window_s=600)

    severity = body.severity or Severity.MEDIUM
    try:
        sev_enum = Severity(severity) if isinstance(severity, str) else severity
    except Exception:
        sev_enum = Severity.MEDIUM

    source_id = "citizen:anonymous"
    if body.qr_payload:
        source_id = f"citizen-qr:{body.qr_payload[:32]}"
    elif body.asset_code:
        source_id = f"citizen:{body.asset_code}"
    elif body.contact:
        source_id = "citizen:contact"

    extra = dict(sanitize_extra(body.extra) or {})
    if body.description:
        extra["citizen_description"] = body.description
    if body.asset_code:
        extra["citizen_asset_code"] = body.asset_code
    if body.qr_payload:
        extra["citizen_qr_payload"] = body.qr_payload
    if body.contact:
        extra["citizen_contact"] = body.contact
    extra["citizen_report"] = True
    extra["ai_status"] = "RULE_BASED"
    extra.update(department_for(EventType.BRIDGE_ANOMALY))

    obs_in = ObservationIn(
        event_type=EventType.BRIDGE_ANOMALY,
        severity=sev_enum,
        latitude=body.latitude,
        longitude=body.longitude,
        gps_accuracy=body.gps_accuracy,
        timestamp=datetime.now(timezone.utc),
        source_type=SourceType.PHONE,
        source_id=source_id,
        confidence=0.65,
        simulated=False,
        extra=extra,
    )
    obs, event, created = ingest_observation(db, obs_in)
    claim = merge_citizen_claim(body.claim_token, event.id)

    notif = NotificationLog(
        title="Citizen bridge report — BRIDGE_ANOMALY",
        message=body.description or f"Citizen report at {body.latitude:.5f},{body.longitude:.5f} severity {sev_enum.value}",
        severity=sev_enum.value,
        event_id=event.id,
        channel="citizen",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)

    return {
        "observation_id": obs.id,
        "event_id": event.id,
        "event_code": event.public_code,
        "created_event": created,
        "notification_id": notif.id,
        "severity": sev_enum.value,
        "claim_token": claim,
        "department": department_for(EventType.BRIDGE_ANOMALY),
        "contact_masked": mask_contact(body.contact) if body.contact else None,
        "honesty": "RULE_BASED",
        "note": "Keep this claim token to see only your tickets. ICCC still sees the folio.",
    }


@router.get("/citizen/tickets")
def citizen_tickets(db: Session = Depends(get_db), claim: str = Query(min_length=8, max_length=4000)):
    try:
        ids = read_citizen_claim(claim)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    rows = []
    for eid in ids:
        event = db.get(UrbanEvent, eid)
        if event is None:
            continue
        body = {
            "id": event.id,
            "public_code": event.public_code,
            "event_type": event.event_type.value if event.event_type else None,
            "severity": event.severity.value if event.severity else None,
            "status": event.status.value if event.status else None,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "created_at": event.created_at,
            "extra": event.extra,
        }
        rows.append(sanitize_event(body, None))
    return {"honesty": "RULE_BASED", "count": len(rows), "items": rows}
