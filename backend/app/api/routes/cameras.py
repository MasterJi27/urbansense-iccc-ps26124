"""Register and ingest stills from any CCTV / DVR. Push stills — no UrbanSense hardware."""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.routes.ingest import _ingest, _vision_observation
from app.database import get_db
from app.deps import ROLE_RANK, get_current_user, require_roles
from app.models.event import SourceType
from app.models.fleet import Bus, ProcessingMode, SensorNode
from app.models.user import User, UserRole
from app.schemas.common import CameraIn, CameraPullIn
from app.services.azure_edge import StillRejected
from app.services.camera_bridge import assert_snapshot_url, fetch_snapshot, lan_pull_enabled, public_presets

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _kind(raw: str | None) -> SourceType:
    return SourceType.ROAD_CCTV if (raw or "").upper() == "ROAD_CCTV" else SourceType.BUS_CCTV


def _upsert_node(db: Session, body: CameraIn) -> SensorNode:
    code = body.code.strip().upper().replace(" ", "-")
    node = db.query(SensorNode).filter(SensorNode.code == code).first()
    if node is None:
        node = SensorNode(code=code)
        db.add(node)
        db.flush()
    kind = _kind(body.kind)
    bay = (body.bay or "FRONT").upper()
    node.device_label = (body.label or f"{body.vendor}_{bay}").upper()
    node.source_type = kind.value
    node.processing_mode = ProcessingMode.CAPTURE_AND_SENSOR
    node.ai_mode = f"CCTV_{(body.vendor or 'GENERIC').upper()}"
    node.network_type = "BRIDGE"
    node.camera_status = "ONLINE"
    if body.bus_code:
        bus = db.query(Bus).filter(Bus.code == body.bus_code.upper()).first()
        if bus:
            node.bus_id = bus.id
    db.commit()
    db.refresh(node)
    return node


def _node_out(db: Session, node: SensorNode) -> dict:
    bus = db.get(Bus, node.bus_id) if node.bus_id else None
    return {
        "id": node.id,
        "code": node.code,
        "bus_code": bus.code if bus else None,
        "device_label": node.device_label,
        "source_type": node.source_type,
        "camera_status": node.camera_status,
        "ai_mode": node.ai_mode,
        "last_heartbeat_at": node.last_heartbeat_at,
        "network_type": node.network_type,
    }


@router.get("/presets")
def camera_presets(_: User = Depends(get_current_user)):
    return {
        "note": "Any camera that can emit one JPEG. Azure does not decode RTSP. Depot 24×7 is scripts/cctv-bridge.ps1 -Loop on the PC next to the DVR, not App Service GPU.",
        "lan_pull": lan_pull_enabled(),
        "items": public_presets(),
    }


@router.get("")
def list_cameras(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = (
        db.query(SensorNode)
        .filter(SensorNode.source_type.in_((SourceType.BUS_CCTV.value, SourceType.ROAD_CCTV.value, "BUS_CCTV", "ROAD_CCTV")))
        .all()
    )
    return [_node_out(db, n) for n in rows]


@router.post("")
def register_camera(body: CameraIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if getattr(user, "auth_scope", "iccc") != "field" and ROLE_RANK.get(user.role, 0) < ROLE_RANK[UserRole.INSPECTOR]:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return _node_out(db, _upsert_node(db, body))


@router.post("/pull")
async def pull_camera_snapshot(
    body: CameraPullIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.INSPECTOR)),
):
    try:
        assert_snapshot_url(body.snapshot_url)
        data = fetch_snapshot(body.snapshot_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    node = _upsert_node(
        db,
        CameraIn(code=body.code, vendor=body.vendor, bay=body.bay, bus_code=body.bus_code, kind=body.kind),
    )
    kind = _kind(body.kind)
    try:
        obs, _vision, _safety, _url = _vision_observation(
            data,
            f"{node.code}.jpg",
            latitude=body.latitude,
            longitude=body.longitude,
            gps_accuracy=None,
            source_id=node.code,
            bus_id=body.bus_code,
            heading=None,
            speed_kmh=None,
            imu_mag=None,
            camera_bay=body.bay,
            source_type=kind,
        )
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    extra = dict(obs.extra or {})
    extra["vendor"] = (body.vendor or "HTTP_SNAPSHOT").upper()
    extra["connector"] = "any-camera-bridge"
    if extra.get("method") != "azure-rdd-onnx":
        extra["method"] = "cctv-http-snapshot"
        extra["derivation"] = "HTTP JPEG snapshot from a DVR/ONVIF URL. Not RTSP decode. Password is not stored."
    obs.extra = extra
    node.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()
    return await _ingest(obs, kind, db, user, background)
