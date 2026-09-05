"""Citizen QR report — no auth, creates BRIDGE_ANOMALY observation."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.event import EventType, Severity, SourceType
from app.models.ops import NotificationLog
from app.schemas.common import CitizenReportIn, ObservationIn

router = APIRouter(tags=["citizen"])


@router.post("/citizen/report")
def citizen_report(body: CitizenReportIn, db: Session = Depends(get_db)):
    # Force BRIDGE_ANOMALY regardless of input
    from app.services.observations import ingest_observation

    severity = body.severity or Severity.MEDIUM
    # keep severity within expected values
    try:
        sev_enum = Severity(severity) if isinstance(severity, str) else severity
    except Exception:
        sev_enum = Severity.MEDIUM

    source_id = f"citizen:{body.contact or 'anonymous'}"
    if body.qr_payload:
        source_id = f"citizen-qr:{body.qr_payload[:32]}"
    elif body.asset_code:
        source_id = f"citizen:{body.asset_code}:{body.contact or 'anonymous'}"

    extra = dict(body.extra or {})
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

    # Simple in-app notification log for citizen report
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
    }
