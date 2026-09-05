import hashlib
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.asset import Asset, AssetType
from app.models.event import SourceType
from app.models.user import User
from app.models.shm import BridgeHealthLog
from app.schemas.common import BridgeBatchIn
from app.services.bridge_shm import AccelSample, BRIDGE_GEOFENCE_M, ingest_bridge_batch

router = APIRouter(tags=["bridge-shm"])

@router.post("/bridge/batch")
def bridge_batch(body: BridgeBatchIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    samples = [AccelSample(t=float(s.get("t", 0)), ax=float(s.get("ax", 0)), ay=float(s.get("ay", 0)), az=float(s.get("az", 0))) for s in body.samples[:800]]
    res = ingest_bridge_batch(
        db,
        samples=samples,
        lat=body.latitude, lon=body.longitude,
        gps_accuracy=body.gps_accuracy, speed_kmh=body.speed_kmh,
        source_type=SourceType(body.source_type) if isinstance(body.source_type, str) else body.source_type,
        source_id=body.source_id, sensor_id=body.sensor_id, bus_id=body.bus_id, route_id=body.route_id,
        simulated=body.simulated, temp_c=(body.extra.get("temp_c") if body.extra else None) if hasattr(body, 'extra') else None,
    )
    return res

@router.get("/bridge/health")
def bridge_health(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    bridges = db.query(Asset).filter(Asset.asset_type.in_([AssetType.BRIDGE, AssetType.FLYOVER])).order_by(Asset.health_score).all()
    return [
        {
            "id": b.id, "code": b.code, "name": b.name, "asset_type": b.asset_type.value,
            "latitude": b.latitude, "longitude": b.longitude,
            "condition": b.condition.value, "health_score": b.health_score,
            "span_m": b.span_m, "baseline_rms": b.shm_baseline_rms, "last_rms": b.shm_last_rms,
            "baseline_freq": b.shm_baseline_freq, "last_freq": b.shm_last_freq,
            "anomaly_count": b.shm_anomaly_count, "last_checked": b.shm_last_checked,
            "predicted_days": b.predicted_days_to_maintenance, "qr_payload": b.qr_payload,
        } for b in bridges
    ]

@router.get("/bridge/geofence")
def bridge_geofence(_: User = Depends(get_current_user)):
    return {"radius_m": BRIDGE_GEOFENCE_M, "method": "GPS within radius snaps to bridge centroid; robust for low-end GPS (±15m)"}

@router.get("/bridge/{bridge_id}/history")
def bridge_history(bridge_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    bridge = db.get(Asset, bridge_id) or db.query(Asset).filter(Asset.code==bridge_id).first()
    if not bridge: return []
    logs = db.query(BridgeHealthLog).filter(BridgeHealthLog.bridge_id==bridge.id).order_by(BridgeHealthLog.created_at.desc()).limit(80).all()
    return [{"rms":l.rms,"peak":l.peak,"crest":l.crest,"freq":l.dominant_freq,"health":l.health_score,"anomaly":l.anomaly,"at":l.created_at,"source":l.source_id} for l in logs][::-1]

@router.get("/bridge/{bridge_id}/inspect")
def bridge_inspect(bridge_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    bridge = db.get(Asset, bridge_id) or db.query(Asset).filter(Asset.code==bridge_id).first()
    if not bridge: return {"error":"not found"}
    from app.models.event import UrbanEvent
    evs = db.query(UrbanEvent).filter(UrbanEvent.asset_id==bridge.id).order_by(UrbanEvent.created_at.desc()).limit(10).all()
    return {"bridge": bridge.code, "visual_checks": ["joint gap","bearing","crack","waterlogging under-deck"], "note":"Camera joint check is visual (RULE_BASED), not ML crack segmentation", "events": [{"code":e.public_code,"type":e.event_type.value,"sev":e.severity.value} for e in evs]}

def _mock_visual_assessment(bridge: Asset) -> dict:
    # Deterministic mock per bridge id so dashboard is stable across reloads
    h = int(hashlib.md5(bridge.id.encode()).hexdigest()[:8], 16)
    rng = random.Random(h)
    # health_score nudges mock toward worse values when low
    health = float(bridge.health_score or 70)
    health_factor = max(0, (70 - health) / 70)  # 0..1 when degrading
    joint_gap_mm = round(rng.uniform(9.5, 18.5) + health_factor * rng.uniform(3, 7), 1)
    # bearing: GOOD/FAIR/WORN/CRITICAL weighted by health
    if health < 40:
        bearing_options = ["WORN", "CRITICAL", "FAIR"]
        weights = [0.4, 0.35, 0.25]
    elif health < 65:
        bearing_options = ["GOOD", "FAIR", "WORN"]
        weights = [0.25, 0.45, 0.30]
    else:
        bearing_options = ["GOOD", "FAIR", "WORN"]
        weights = [0.65, 0.30, 0.05]
    bearing = rng.choices(bearing_options, weights=weights, k=1)[0]
    bearing_displacement_mm = round(rng.uniform(0.2, 1.8) + health_factor * rng.uniform(0.8, 2.5), 1)
    crack_length_mm = round(rng.uniform(0, 90) + health_factor * rng.uniform(40, 220) + (rng.random() < 0.12) * rng.uniform(80, 200), 1)
    crack_severity = "LOW" if crack_length_mm < 50 else "MEDIUM" if crack_length_mm < 150 else "HIGH"
    # waterlogging under deck — more likely after monsoon / low health
    under_deck = rng.random() < (0.18 + health_factor * 0.35)
    depth_mm = round(rng.uniform(8, 45) if under_deck else rng.uniform(0, 4), 1)
    water_severity = "HIGH" if under_deck and depth_mm > 25 else "MEDIUM" if under_deck and depth_mm > 12 else "LOW" if under_deck else "NONE"
    return {
        "joint_gap_mm": joint_gap_mm,
        "joint_gap_status": "ALERT" if joint_gap_mm > 20 else "WATCH" if joint_gap_mm > 16 else "OK",
        "bearing": bearing,
        "bearing_condition": bearing,
        "bearing_displacement_mm": bearing_displacement_mm,
        "bearing_status": bearing,
        "crack_length_mm": crack_length_mm,
        "crack_length": crack_length_mm,
        "crack_severity": crack_severity,
        "waterlogging": {
            "under_deck": under_deck,
            "waterlogging_under_deck": under_deck,
            "depth_mm": depth_mm,
            "severity": water_severity,
            "badge": "WATERLOGGED" if under_deck else "DRY",
        },
        "waterlogging_under_deck": under_deck,
        "under_deck_waterlogging": under_deck,
        "waterlogging_depth_mm": depth_mm,
    }


@router.get("/bridge/{bridge_id}/visual-check")
def bridge_visual_check(bridge_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    bridge = db.get(Asset, bridge_id) or db.query(Asset).filter(Asset.code == bridge_id).first()
    if not bridge:
        return {"error": "not found"}
    mock = _mock_visual_assessment(bridge)
    now = datetime.now(timezone.utc).isoformat()
    # joint photo placeholder — static placeholder (RULE_BASED visual, not ML segmentation)
    joint_photo_placeholder = f"https://via.placeholder.com/320x180.png?text=Joint+{bridge.code}"
    return {
        "bridge_id": bridge.id,
        "bridge_code": bridge.code,
        "bridge_name": bridge.name,
        "checked_at": now,
        "mock": True,
        "method": "RULE_BASED mock visual — not ML crack segmentation; joint photo is placeholder",
        "note": "Mock visual assessment for SHM: joint/bearing/crack are simulated, waterlogging under-deck is flag",
        "joint_gap_mm": mock["joint_gap_mm"],
        "joint_gap_status": mock["joint_gap_status"],
        "bearing": mock["bearing"],
        "bearing_condition": mock["bearing_condition"],
        "bearing_displacement_mm": mock["bearing_displacement_mm"],
        "bearing_status": mock["bearing_status"],
        "crack_length_mm": mock["crack_length_mm"],
        "crack_length": mock["crack_length"],
        "crack_severity": mock["crack_severity"],
        "waterlogging": mock["waterlogging"],
        "waterlogging_under_deck": mock["waterlogging_under_deck"],
        "under_deck_waterlogging": mock["under_deck_waterlogging"],
        "waterlogging_depth_mm": mock["waterlogging_depth_mm"],
        "waterlogging_flag_under_deck": mock["waterlogging_under_deck"],
        "joint_photo_placeholder": joint_photo_placeholder,
        "joint_photo_url": joint_photo_placeholder,
        "assessment": mock,
        "visual_assessment": mock,
    }
