import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.event import SourceType
from app.models.fleet import Bus, ProcessingMode, Route, SensorNode, Trip
from app.models.user import User, UserRole
from app.realtime.hub import hub
from app.schemas.common import BusIn, HeartbeatIn, SensorBindIn, TripIn
from app.services.fusion import record_clear_passes
from app.services.refs import ensure_bus


_IMU_WIRE = ("imu_mag", "imu_ax", "imu_ay", "imu_az", "gyro_z", "gps_accuracy", "gps_ok")


def _live_telemetry(src) -> dict:
    def _get(key):
        if isinstance(src, dict):
            return src.get(key)
        return getattr(src, key, None)

    return {key: _get(key) for key in _IMU_WIRE}


def _clip_live_boxes(rows: list | None) -> list[dict]:
    out: list[dict] = []
    for row in (rows or [])[:12]:
        if not isinstance(row, dict):
            continue
        bbox = row.get("bbox") or []
        if len(bbox) < 4:
            continue
        try:
            out.append(
                {
                    "klass": str(row.get("klass") or row.get("event_type") or "")[:64],
                    "event_type": str(row.get("event_type") or "")[:32],
                    "confidence": float(row.get("confidence") or 0),
                    "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                }
            )
            tid = str(row.get("track_id") or "")[:32]
            if tid:
                out[-1]["track_id"] = tid
            hits = row.get("hits")
            if hits is not None:
                out[-1]["hits"] = max(0, min(int(hits), 999))
        except (TypeError, ValueError):
            continue
    return out


def _parse_boxes(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


router = APIRouter(tags=["fleet"])


@router.get("/buses")
def list_buses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    buses = db.query(Bus).all()
    sensors = db.query(SensorNode).all()
    by_bus: dict[str, list] = {}
    for s in sensors:
        if not s.bus_id:
            continue
        by_bus.setdefault(s.bus_id, []).append(
            {"code": s.code, "device_label": s.device_label, "camera_status": s.camera_status}
        )
    return [
        {
            "id": b.id,
            "code": b.code,
            "registration": b.registration,
            "route_id": b.route_id,
            "qr_payload": b.qr_payload,
            "active": b.active,
            "camera_bays": by_bus.get(b.id, []),
        }
        for b in buses
    ]


@router.post("/buses")
def create_bus(body: BusIn, db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    if db.query(Bus).filter(Bus.code == body.code).first():
        raise HTTPException(409, "Bus code exists")
    bus = Bus(code=body.code, registration=body.registration, route_id=body.route_id, qr_payload=f"urbansense://bus/{body.code}")
    db.add(bus)
    db.commit()
    db.refresh(bus)
    return {"id": bus.id, "code": bus.code, "qr_payload": bus.qr_payload}


@router.get("/routes")
def list_routes(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "planned_duration_minutes": r.planned_duration_minutes,
            "simulated": r.simulated,
            "polyline": r.polyline,
        }
        for r in db.query(Route).all()
    ]


@router.get("/sensor-nodes")
def list_sensors(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    out = []
    for s in db.query(SensorNode).all():
        bus = db.get(Bus, s.bus_id) if s.bus_id else None
        out.append(
            {
                "id": s.id,
                "code": s.code,
                "bus_id": s.bus_id,
                "bus_code": bus.code if bus else None,
                "device_label": s.device_label,
                "source_type": s.source_type,
                "processing_mode": s.processing_mode.value,
                "camera_status": s.camera_status,
                "gps_status": s.gps_status,
                "imu_status": s.imu_status,
                "battery_pct": s.battery_pct,
                "temperature_c": s.temperature_c,
                "storage_free_mb": s.storage_free_mb,
                "network_type": s.network_type,
                "ai_mode": s.ai_mode,
                "last_heartbeat_at": s.last_heartbeat_at,
                "sync_state": s.sync_state,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "heading": s.heading,
                "speed_kmh": s.speed_kmh,
                "last_boxes": _parse_boxes(s.last_boxes_json),
                "person_count": s.person_count,
                "overlay_fps": s.overlay_fps,
            }
        )
    return out



@router.post("/sensor-nodes")
def create_sensor(body: SensorBindIn, db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    node = db.query(SensorNode).filter(SensorNode.code == body.sensor_code).first()
    if not node:
        node = SensorNode(code=body.sensor_code, device_label=body.device_label)
        db.add(node)
        db.flush()
    bus = db.query(Bus).filter(Bus.code == body.bus_code).first()
    if not bus:
        raise HTTPException(404, "Bus not found")
    node.bus_id = bus.id
    node.device_label = body.device_label
    db.commit()
    db.refresh(node)
    return {"id": node.id, "code": node.code, "bus_id": node.bus_id, "bus_code": bus.code}


@router.post("/sensor-nodes/bind")
def bind_sensor(body: SensorBindIn, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ADMIN))):
    return create_sensor(body, db, user)


@router.post("/sensor-nodes/heartbeat")
def heartbeat(
    body: HeartbeatIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    node = None
    if body.sensor_id:
        node = db.get(SensorNode, body.sensor_id)
    if node is None and body.sensor_code:
        node = db.query(SensorNode).filter(SensorNode.code == body.sensor_code).first()
    if node is None:
        node = SensorNode(code=body.sensor_code or f"NODE-{datetime.now(timezone.utc).strftime('%H%M%S')}")
        db.add(node)
        db.flush()
    bus_code = None
    if body.bus_code:
        try:
            bus = ensure_bus(db, body.bus_code)
            node.bus_id = bus.id
            bus_code = bus.code
        except ValueError:
            bus_code = None
    node.camera_status = body.camera_status
    node.gps_status = body.gps_status
    node.imu_status = body.imu_status
    node.battery_pct = body.battery_pct
    node.temperature_c = body.temperature_c
    node.storage_free_mb = body.storage_free_mb
    node.network_type = body.network_type
    node.ai_mode = body.ai_mode
    node.sync_state = body.sync_state
    if body.latitude is not None:
        node.latitude = body.latitude
    if body.longitude is not None:
        node.longitude = body.longitude
    node.heading = body.heading
    node.speed_kmh = body.speed_kmh
    node.last_heartbeat_at = datetime.now(timezone.utc)
    boxes = _clip_live_boxes(body.last_boxes)
    if body.last_boxes is not None:
        node.last_boxes_json = json.dumps(boxes)
    if body.person_count is not None:
        node.person_count = int(body.person_count)
    if body.overlay_fps is not None:
        node.overlay_fps = float(body.overlay_fps)
    if body.processing_mode:
        try:
            node.processing_mode = ProcessingMode(body.processing_mode)
        except ValueError:
            pass
    bay = None
    label = (node.device_label or "").upper()
    if "CABIN" in label:
        bay = "CABIN"
    elif "FRONT" in label:
        bay = "FRONT"
    elif "REAR" in label:
        bay = "REAR"
    source_id = bus_code or body.bus_code or node.code
    clear = record_clear_passes(
        db,
        latitude=body.latitude if body.latitude is not None else node.latitude,
        longitude=body.longitude if body.longitude is not None else node.longitude,
        source_id=source_id,
        heading=body.heading,
        camera_bay=bay,
        source_type=SourceType.PHONE,
    )
    db.commit()
    telemetry = _live_telemetry(body)
    live = {
        "type": "live.heartbeat",
        "sensor_id": node.id,
        "sensor_code": node.code,
        "bus_code": bus_code or body.bus_code,
        "latitude": node.latitude,
        "longitude": node.longitude,
        "heading": node.heading,
        "last_boxes": boxes if body.last_boxes is not None else _parse_boxes(node.last_boxes_json),
        "person_count": node.person_count or 0,
        "overlay_fps": node.overlay_fps,
        "overlay_mode": body.overlay_mode,
        "overlay_backend": body.overlay_backend,
        "infer_ms": body.infer_ms,
        "ai_mode": node.ai_mode,
        **telemetry,
    }
    background.add_task(hub.broadcast, live, "live")
    return {
        "ok": True,
        "sensor_id": node.id,
        "sensor_code": node.code,
        "bus_code": bus_code or body.bus_code,
        "last_heartbeat_at": node.last_heartbeat_at,
        "clear_passes": clear,
        "latitude": node.latitude,
        "longitude": node.longitude,
        **telemetry,
    }


@router.get("/fleet/live")
def fleet_live(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return list_sensors(db, _)


@router.post("/trips")
def start_trip(body: TripIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    trip = Trip(bus_id=body.bus_id, sensor_id=body.sensor_id, route_id=body.route_id, simulated=body.simulated)
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return {"id": trip.id, "started_at": trip.started_at, "bus_id": trip.bus_id}


@router.post("/trips/{trip_id}/stop")
def stop_trip(trip_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    trip = db.get(Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    trip.ended_at = datetime.now(timezone.utc)
    trip.actual_duration_minutes = (trip.ended_at - trip.started_at.replace(tzinfo=timezone.utc)).total_seconds() / 60
    db.commit()
    return {"id": trip.id, "ended_at": trip.ended_at, "actual_duration_minutes": trip.actual_duration_minutes}
