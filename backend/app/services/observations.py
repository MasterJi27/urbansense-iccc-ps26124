import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import get_settings
from app.files import safe_filename
from app.geo import validate_coords
from app.models.event import Observation, UrbanEvent
from app.models.ops import SyncLog
from app.realtime.hub import hub
from app.schemas.common import EventOut, ObservationIn
from app.services.audit import audit
from app.services.azure_edge import save_evidence_blob
from app.services.composio_notify import notify_fleet_confirmed
from app.services.departments import attach_department
from app.services.extras import sanitize_extra
from app.services.fusion import FusionEngine, default_engine
from app.services.refs import coerce_bus_id
from app.services.road_health import recompute_road_health


def _sanitize_evidence_filename(filename: str) -> str:
    return safe_filename(filename)


def ingest_observation(
    db: Session,
    payload: ObservationIn,
    actor_id: str | None = None,
    engine: FusionEngine | None = None,
) -> tuple[Observation, UrbanEvent, bool]:
    validate_coords(payload.latitude, payload.longitude)
    ts = payload.timestamp or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    bus_fk = coerce_bus_id(db, payload.bus_id)
    obs = Observation(
        event_type=payload.event_type,
        severity=payload.severity,
        latitude=payload.latitude,
        longitude=payload.longitude,
        gps_accuracy=payload.gps_accuracy,
        timestamp=ts,
        source_type=payload.source_type,
        source_id=payload.source_id,
        sensor_id=payload.sensor_id,
        bus_id=bus_fk,
        route_id=payload.route_id,
        confidence=payload.confidence,
        simulated=payload.simulated,
        heading=payload.heading,
        speed_kmh=payload.speed_kmh,
        plate_text=payload.plate_text,
        plate_confidence=payload.plate_confidence,
        evidence_url=payload.evidence_url,
        thumbnail_url=payload.thumbnail_url,
        extra=sanitize_extra(payload.extra),
    )
    db.add(obs)
    db.flush()
    fusion = (engine or default_engine()).fuse(db, obs)
    db.add(
        SyncLog(
            sensor_id=payload.sensor_id,
            client_event_id=payload.client_id,
            status="OK",
            detail=f"observation={obs.id} event={fusion.event.id} created={fusion.created}",
        )
    )
    audit(
        db,
        "observation.ingest",
        "observation",
        obs.id,
        actor_id=actor_id,
        detail=fusion.reason,
    )
    recompute_road_health(db)
    attach_department(fusion.event)
    db.commit()
    db.refresh(fusion.event)
    extra = fusion.event.extra or {}
    if extra.get("patrol_state") == "FLEET_CONFIRMED" and (fusion.event.source_count or 0) == 2:
        notify_fleet_confirmed(fusion.event)
    return obs, fusion.event, fusion.created


async def publish_event(event: UrbanEvent, created: bool) -> None:
    body = EventOut.model_validate(event).model_dump(mode="json")
    await hub.broadcast({"type": "event.created" if created else "event.updated", "event": body})


def save_evidence_bytes(filename: str, data: bytes) -> str:
    settings = get_settings()
    directory = Path(settings.evidence_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    safe = f"{stamp}-{uuid4().hex[:8]}-{_sanitize_evidence_filename(filename)}"
    path = (directory / safe).resolve()
    # ensure resolved path is within evidence directory (prevent traversal)
    try:
        path.relative_to(directory)
    except ValueError:
        raise ValueError("invalid filename: traversal blocked")
    path.write_bytes(data)
    try:
        blob_url = save_evidence_blob(safe, data)
        if blob_url:
            logging.getLogger("urbansense.azure").info("evidence also stored on blob")
    except Exception:
        logging.getLogger("urbansense.azure").exception("blob upload skipped")
    return f"{settings.public_base_url.rstrip('/')}/evidence/{safe}"
