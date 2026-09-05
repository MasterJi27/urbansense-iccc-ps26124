"""Unified ingestion gateway. Future CCTV/IoT devices post the same Observation model."""

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.event import EventType, Severity, SourceType
from app.models.user import User
from app.schemas.common import ObservationIn, ObservationOut, EventOut
from app.services.dpdp import sanitize_event, sanitize_observation
from app.services.azure_edge import (
    StillRejected,
    analyze_still,
    azure_stack_status,
    read_still,
    screen_still,
    validate_still,
)
from app.services.observations import ingest_observation, publish_event, save_evidence_bytes
from app.services.ps26124 import apply_camera_bay

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def _ingest(body: ObservationIn, source: SourceType, db: Session, user: User, background: BackgroundTasks):
    body.source_type = source
    try:
        obs, event, created = ingest_observation(db, body, actor_id=user.id)
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Could not store observation. Bus/source link was invalid.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(publish_event, event, created)
    return {
        "observation": sanitize_observation(ObservationOut.model_validate(obs).model_dump(mode="json"), user),
        "event": sanitize_event(EventOut.model_validate(event).model_dump(mode="json"), user),
        "created_event": created,
    }


@router.post("/phone")
async def ingest_phone(body: ObservationIn, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return await _ingest(body, SourceType.PHONE, db, user, background)


@router.post("/cctv")
async def ingest_cctv(body: ObservationIn, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return await _ingest(body, SourceType.BUS_CCTV if body.source_type != SourceType.ROAD_CCTV else SourceType.ROAD_CCTV, db, user, background)


@router.post("/iot")
async def ingest_iot(body: ObservationIn, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return await _ingest(body, SourceType.IOT, db, user, background)


@router.get("/edge/status")
def edge_status(_: User = Depends(get_current_user)):
    return azure_stack_status()


def _vision_observation(data: bytes, name: str, *, latitude, longitude, gps_accuracy, source_id, bus_id, heading, speed_kmh, imu_mag, camera_bay: str = "FRONT", source_type: SourceType = SourceType.PHONE):
    validate_still(data)
    try:
        safety = screen_still(data)
    except Exception as exc:
        safety = {"ok": True, "ai_status": "DISABLED", "skipped": True, "reason": str(exc)}
    if not safety.get("ok"):
        raise HTTPException(status_code=400, detail={"reason": "content_safety_blocked", "categories": safety.get("blocked")})
    url = save_evidence_bytes(name, data)
    try:
        vision = analyze_still(data)
    except Exception as exc:
        vision = {"ok": False, "ai_status": "DISABLED", "reason": str(exc)}

    mapped = vision.get("mapped_event_type") if vision.get("ok") else None
    event_type = EventType(mapped) if mapped else EventType.OTHER
    bay = (camera_bay or "FRONT").upper()
    if not mapped and imu_mag is not None and bay != "CABIN":
        event_type = EventType.POTHOLE
    event_type, bay_note = apply_camera_bay(event_type, bay)
    sev_raw = vision.get("mapped_severity") if vision.get("ok") else None
    severity = Severity(sev_raw) if sev_raw else (Severity.HIGH if event_type == EventType.POTHOLE else Severity.MEDIUM)
    extra: dict = {
        "method": "azure-ai-vision" if vision.get("ok") else "phone-still",
        "model": vision.get("model") or "none",
        "provider": vision.get("provider") or "local",
        "ai_status": vision.get("ai_status") or "DISABLED",
        "engine_status": vision.get("engine_status") or "RULE_BASED",
        "caption": vision.get("caption"),
        "azure_tags": vision.get("tags") or [],
        "azure_vision": vision,
        "content_safety": safety,
        "imu_mag": imu_mag,
        "patrol": True,
        "camera_bay": bay,
        "derivation": (
            "Azure AI Vision caption/tags mapped to an UrbanSense type. Not RDD YOLO and not a dedicated waterlogging net."
            if vision.get("ok")
            else "Phone still stored. Azure Vision not configured — type from IMU fallback or OTHER."
        ),
    }
    if event_type == EventType.WATERLOGGING:
        extra["derivation"] = (
            "Azure Vision tags mentioned water/flood. This is cloud image analysis, not a trained waterlogging detector."
        )
    if bay_note:
        extra["derivation"] = bay_note
        extra["engine_status"] = "RULE_BASED"
    body = ObservationIn(
        event_type=event_type,
        severity=severity,
        latitude=latitude,
        longitude=longitude,
        gps_accuracy=gps_accuracy,
        source_type=source_type,
        source_id=source_id,
        bus_id=bus_id or None,
        confidence=0.62 if vision.get("ok") else 0.45,
        simulated=False,
        heading=heading,
        speed_kmh=speed_kmh,
        evidence_url=url,
        extra=extra,
        client_id=f"phone-still-{name}",
    )
    return body, vision, safety, url


@router.post("/phone/probe")
async def probe_phone_still(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    try:
        data = await read_still(file)
        safety = screen_still(data)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    vision = {"ok": False, "ai_status": "DISABLED"}
    if safety.get("ok"):
        try:
            vision = analyze_still(data)
        except Exception as exc:
            vision = {"ok": False, "ai_status": "DISABLED", "reason": str(exc)}
    return {
        "ok": bool(safety.get("ok")),
        "ingested": False,
        "bytes": len(data),
        "content_safety": safety,
        "vision": vision,
        "stack": azure_stack_status(),
        "checked_by": user.email,
    }


@router.post("/phone/still")
async def ingest_phone_still(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: float = Form(28.6328),
    longitude: float = Form(77.2195),
    gps_accuracy: float | None = Form(None),
    source_id: str = Form("NODE-PHONE-01"),
    bus_id: str | None = Form(None),
    heading: float | None = Form(None),
    speed_kmh: float | None = Form(None),
    imu_mag: float | None = Form(None),
    camera_bay: str = Form("FRONT"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = await read_still(file)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = file.filename or "phone-still.jpg"
    try:
        body, _vision, _safety, _url = _vision_observation(
            data,
            name,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy=gps_accuracy,
            source_id=source_id,
            bus_id=bus_id,
            heading=heading,
            speed_kmh=speed_kmh,
            imu_mag=imu_mag,
            camera_bay=camera_bay,
            source_type=SourceType.PHONE,
        )
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _ingest(body, SourceType.PHONE, db, user, background)


@router.post("/cctv/still")
async def ingest_cctv_still(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: float = Form(28.6328),
    longitude: float = Form(77.2195),
    gps_accuracy: float | None = Form(None),
    source_id: str = Form("CAM-DVR-01"),
    bus_id: str | None = Form(None),
    heading: float | None = Form(None),
    speed_kmh: float | None = Form(None),
    camera_bay: str = Form("FRONT"),
    vendor: str = Form("GENERIC"),
    source_kind: str = Form("BUS_CCTV"),
    imu_mag: float | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kind = SourceType.ROAD_CCTV if (source_kind or "").upper() == "ROAD_CCTV" else SourceType.BUS_CCTV
    try:
        data = await read_still(file)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = file.filename or "cctv-still.jpg"
    try:
        body, _vision, _safety, _url = _vision_observation(
            data,
            name,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy=gps_accuracy,
            source_id=source_id,
            bus_id=bus_id,
            heading=heading,
            speed_kmh=speed_kmh,
            imu_mag=imu_mag,
            camera_bay=camera_bay,
            source_type=kind,
        )
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    extra = dict(body.extra or {})
    extra.update(
        {
            "method": "cctv-still",
            "vendor": (vendor or "GENERIC").upper(),
            "connector": "any-camera-bridge",
            "derivation": extra.get("derivation")
            or "One JPEG from an arbitrary camera/DVR. Not a live NVR stream and not continuous YOLO.",
        }
    )
    body.extra = extra
    return await _ingest(body, kind, db, user, background)


@router.post("/bus/stream-frame")
async def ingest_bus_stream_frame(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: float = Form(28.6328),
    longitude: float = Form(77.2195),
    gps_accuracy: float | None = Form(None),
    source_id: str = Form("BUS-042-FRONT"),
    bus_id: str | None = Form(None),
    heading: float | None = Form(None),
    speed_kmh: float | None = Form(None),
    camera_bay: str = Form("FRONT"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = await read_still(file)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = file.filename or "bus-frame.jpg"
    try:
        body, _vision, _safety, _url = _vision_observation(
            data,
            name,
            latitude=latitude,
            longitude=longitude,
            gps_accuracy=gps_accuracy,
            source_id=source_id,
            bus_id=bus_id,
            heading=heading,
            speed_kmh=speed_kmh,
            imu_mag=None,
            camera_bay=camera_bay,
            source_type=SourceType.BUS_CCTV,
        )
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _ingest(body, SourceType.BUS_CCTV, db, user, background)
