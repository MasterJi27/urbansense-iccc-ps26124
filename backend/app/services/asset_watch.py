"""GIS-derived missing-infrastructure watch (RULE_BASED / GIS_DERIVED).

A normal object detector cannot prove absence. Instead UrbanSense compares
camera passes against EXPECTED assets from its own asset/GIS database:

    expected asset (SIGN-183 STOP at X,Y)
      + N bus passes within PASS_RADIUS_M
      + zero visual confirmations
      + no already-open matching event nearby
        -> ONE possible-missing/damaged Observation -> Fusion -> UrbanEvent

Thresholds are explicit and configurable; nothing here is a trained model.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.geo import haversine_m, validate_coords
from app.models.asset import Asset, AssetPass, AssetType
from app.models.event import EventStatus, EventType, Severity, SourceType, UrbanEvent
from app.schemas.common import ObservationIn
from app.services.observations import ingest_observation

PASS_RADIUS_M = 60.0
PASSES_REQUIRED = 3
PASS_WINDOW_DAYS = 7

# Asset type -> UrbanEvent type raised when the asset is repeatedly not seen.
ASSET_TO_EVENT: dict[AssetType, EventType] = {
    AssetType.TRAFFIC_SIGN: EventType.DAMAGED_SIGN,
    AssetType.DIVIDER: EventType.MISSING_DIVIDER,
    AssetType.ZEBRA_CROSSING: EventType.MISSING_ZEBRA,
}


def record_pass(    db: Session,
    asset: Asset,
    latitude: float,
    longitude: float,
    observed: bool,
    source_type: str = "PHONE",
    source_id: str = "",
    actor_id: str | None = None,
) -> dict:
    """Record one pass and maybe raise a GIS-derived missing-asset event."""
    validate_coords(latitude, longitude)
    db.add(
        AssetPass(
            asset_id=asset.id,
            latitude=latitude,
            longitude=longitude,
            observed=observed,
            source_type=source_type,
            source_id=source_id,
        )
    )
    db.flush()

    if observed:
        db.commit()
        return {"raised": False, "reason": "asset visually confirmed on this pass"}

    event_type = ASSET_TO_EVENT.get(asset.asset_type)
    if event_type is None:
        db.commit()
        return {"raised": False, "reason": f"no missing-event mapping for {asset.asset_type.value}"}

    since = datetime.now(timezone.utc) - timedelta(days=PASS_WINDOW_DAYS)
    recent = (
        db.query(AssetPass)
        .filter(AssetPass.asset_id == asset.id, AssetPass.created_at >= since)
        .all()
    )
    nearby = [
        p
        for p in recent
        if haversine_m(latitude, longitude, p.latitude, p.longitude) <= PASS_RADIUS_M
        and haversine_m(asset.latitude, asset.longitude, p.latitude, p.longitude) <= PASS_RADIUS_M
    ]
    confirmed = [p for p in nearby if p.observed]
    if confirmed:
        db.commit()
        return {"raised": False, "reason": "asset confirmed on a recent pass"}
    if len(nearby) < PASSES_REQUIRED:
        db.commit()
        return {
            "raised": False,
            "reason": f"{len(nearby)}/{PASSES_REQUIRED} non-confirming passes within {PASS_RADIUS_M:.0f}m",
        }

    open_statuses = [
        EventStatus.UNVERIFIED,
        EventStatus.CONFIRMED,
        EventStatus.ASSIGNED,
        EventStatus.IN_PROGRESS,
        EventStatus.RE_VERIFICATION,
        EventStatus.REOPENED,
    ]
    for ev in db.query(UrbanEvent).filter(UrbanEvent.status.in_(open_statuses)).all():
        if (
            ev.event_type == event_type
            and haversine_m(asset.latitude, asset.longitude, ev.latitude, ev.longitude) <= PASS_RADIUS_M
        ):
            db.commit()
            return {"raised": False, "reason": f"open {ev.public_code} already covers this asset"}

    obs, event, _ = ingest_observation(
        db,
        ObservationIn(
            event_type=event_type,
            severity=Severity.MEDIUM,
            latitude=asset.latitude,
            longitude=asset.longitude,
            gps_accuracy=10.0,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType(source_type) if source_type in SourceType.__members__ else SourceType.PHONE,
            source_id=source_id or "ASSET-WATCH",
            confidence=0.6,
            simulated=False,
            extra={
                "ai_status": "RULE_BASED",
                "derivation": "GIS_ASSET_WATCH",
                "method": "expected-asset vs camera passes",
                "asset_code": asset.code,
                "asset_type": asset.asset_type.value,
                "passes": len(nearby),
                "passes_required": PASSES_REQUIRED,
                "radius_m": PASS_RADIUS_M,
                "note": "Possible missing/damaged infrastructure: expected asset not "
                "visually confirmed on repeated passes. Not a neural absence detector.",
            },
        ),
        actor_id=actor_id,
    )
    db.commit()
    return {"raised": True, "observation_id": obs.id, "event_id": event.id,
            "public_code": event.public_code}
