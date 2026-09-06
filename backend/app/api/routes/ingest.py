"""Unified ingestion gateway. Future CCTV/IoT devices post the same Observation model."""

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from uuid import uuid4

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
    looks_like_video,
    read_still,
    screen_still,
    validate_still,
)
from app.services.place import reverse_place
from app.services.bbox_severity import severity_from_boxes
from app.services.observations import ingest_observation, publish_event, save_evidence_bytes
from app.services.ahead_gps import project_ahead
from app.services.imu_rules import shake_event_type
from app.services.ps26124 import apply_camera_bay
from app.services.rdd_cloud import detect_rdd, rdd_cloud_status, top_event

router = APIRouter(prefix="/ingest", tags=["ingest"])
_STILL_POOL = ThreadPoolExecutor(max_workers=3)
CLIP_MAX_BYTES = 4_000_000


def _safe_analyze_still(data: bytes) -> dict:
    try:
        return analyze_still(data)
    except Exception as exc:
        return {"ok": False, "ai_status": "DISABLED", "reason": str(exc)}



async def _ingest(body: ObservationIn, source: SourceType, db: Session, user: User, background: BackgroundTasks):
    body.source_type = source
    try:
        obs, event, created = ingest_observation(db, body, actor_id=user.id)
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail="Could not store observation. Bus/source link was invalid.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background.add_task(publish_event, event, created)
    extra = body.extra if isinstance(getattr(body, "extra", None), dict) else {}
    return {
        "observation": sanitize_observation(ObservationOut.model_validate(obs).model_dump(mode="json"), user),
        "event": sanitize_event(EventOut.model_validate(event).model_dump(mode="json"), user),
        "created_event": created,
        "detections": extra.get("detections") or [],
        "rdd": extra.get("rdd") or rdd_cloud_status(),
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


def _vision_observation(data: bytes, name: str, *, latitude, longitude, gps_accuracy, source_id, bus_id, heading, speed_kmh, imu_mag, camera_bay: str = "FRONT", source_type: SourceType = SourceType.PHONE, live_photo_url: str | None = None):
    validate_still(data)
    try:
        safety = screen_still(data)
    except Exception as exc:
        safety = {"ok": True, "ai_status": "DISABLED", "skipped": True, "reason": str(exc)}
    if not safety.get("ok"):
        raise HTTPException(status_code=400, detail={"reason": "content_safety_blocked", "categories": safety.get("blocked")})
    url = save_evidence_bytes(name, data)
    t0 = perf_counter()
    rdd_f = _STILL_POOL.submit(detect_rdd, data)
    vis_f = _STILL_POOL.submit(_safe_analyze_still, data)
    place_f = _STILL_POOL.submit(reverse_place, latitude, longitude)
    rdd = rdd_f.result(timeout=60)
    vision = vis_f.result(timeout=60)
    place = place_f.result(timeout=20)
    still_ms = int(round((perf_counter() - t0) * 1000))
    detections = rdd.get("detections") or []
    top = top_event(detections)

    mapped = vision.get("mapped_event_type") if vision.get("ok") else None
    bay = (camera_bay or "FRONT").upper()
    ahead = project_ahead(latitude, longitude, heading, top.get("bbox") if top else None)
    if top:
        event_type = EventType(top["event_type"])
        graded = severity_from_boxes([{"x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3]} for b in [top["bbox"]]], frame_w=1, frame_h=1)
        severity = Severity(top["severity"]) if graded["bbox_frac"] < 0.05 else graded["severity"]
        method = "azure-rdd-onnx"
        ai_status = "REAL"
        engine_status = "REAL"
        model = rdd.get("model") or "YOLOv8s_RDD_india.onnx"
        provider = "Azure App Service"
        confidence = float(top["confidence"])
        derivation = (
            "Azure-hosted RDD YOLO on this still. Pin is walked ahead along heading from the box. "
            "Lens is live; Azure sees sampled frames, not a 24×7 uploaded video."
        )
        latitude = ahead["latitude"]
        longitude = ahead["longitude"]
    else:
        event_type = EventType(mapped) if mapped else EventType.OTHER
        shaken = shake_event_type(imu_mag, speed_kmh, has_box=False) if bay != "CABIN" else None
        if shaken and not mapped:
            event_type = shaken
        sev_raw = vision.get("mapped_severity") if vision.get("ok") else None
        severity = Severity(sev_raw) if sev_raw else (Severity.HIGH if event_type in {EventType.POTHOLE, EventType.RASH_DRIVING} else Severity.MEDIUM)
        method = "azure-ai-vision" if vision.get("ok") else ("phone-imu-shake" if shaken else "phone-still")
        ai_status = vision.get("ai_status") or "DISABLED"
        engine_status = vision.get("engine_status") or "RULE_BASED"
        model = vision.get("model") or "none"
        provider = vision.get("provider") or "azure"
        confidence = 0.62 if vision.get("ok") else (0.5 if shaken else 0.45)
        derivation = (
            "Azure AI Vision caption/tags mapped to an UrbanSense type. RDD found no box on this still."
            if vision.get("ok")
            else (
                "Accelerometer spike. Proximity is near/far only — shake is IMU. Not a crash classifier."
                if shaken
                else "Phone still stored. RDD found no box. Type from IMU fallback or OTHER."
            )
        )
    event_type, bay_note = apply_camera_bay(event_type, bay)
    extra: dict = {
        "payload_kind": "FIELD",
        "method": method,
        "model": model,
        "provider": provider,
        "ai_status": ai_status,
        "engine_status": engine_status,
        "caption": vision.get("caption"),
        "azure_tags": vision.get("tags") or [],
        "azure_vision": vision,
        "rdd": rdd,
        "detections": detections,
        "content_safety": safety,
        "imu_mag": imu_mag,
        "patrol": True,
        "camera_bay": bay,
        "derivation": derivation,
        "gps_ahead": ahead,
        "place": place,
        "live_photo_url": live_photo_url,
        "live_photo": bool(live_photo_url),
        "scan_parallel": True,
        "azure_still_ms": still_ms,
        "rdd_infer_ms": rdd.get("infer_ms"),
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
        confidence=confidence,
        simulated=False,
        heading=heading,
        speed_kmh=speed_kmh,
        evidence_url=url,
        extra=extra,
        client_id=f"phone-still-{uuid4().hex}",
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
    rdd = detect_rdd(data) if safety.get("ok") else {"ok": False, "detections": [], "ai_status": "DISABLED"}
    return {
        "ok": bool(safety.get("ok")),
        "ingested": False,
        "bytes": len(data),
        "content_safety": safety,
        "vision": {
            "ok": False,
            "ai_status": "DISABLED",
            "skipped": True,
            "reason": "Probe is RDD-only so Android/iPhone/CCTV can tick without a Vision round-trip.",
        },
        "rdd": rdd,
        "detections": rdd.get("detections") or [],
        "stack": azure_stack_status(),
        "checked_by": user.email,
    }


@router.post("/phone/still")
async def ingest_phone_still(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    gps_accuracy: float | None = Form(None),
    source_id: str = Form("NODE-PHONE-01"),
    bus_id: str | None = Form(None),
    heading: float | None = Form(None),
    speed_kmh: float | None = Form(None),
    imu_mag: float | None = Form(None),
    camera_bay: str = Form("FRONT"),
    clip: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if latitude is None or longitude is None:
        raise HTTPException(status_code=400, detail="GPS fix required")
    try:
        data = await read_still(file)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = file.filename or "phone-still.jpg"
    live_photo_url = None
    if clip is not None:
        raw = await clip.read(CLIP_MAX_BYTES + 1)
        if raw and len(raw) <= CLIP_MAX_BYTES and looks_like_video(raw):
            live_photo_url = save_evidence_bytes(clip.filename or "live.webm", raw)
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
            live_photo_url=live_photo_url,
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
    extra["vendor"] = (vendor or "GENERIC").upper()
    extra["connector"] = "any-camera-bridge"
    if extra.get("method") != "azure-rdd-onnx":
        extra["method"] = "cctv-still"
        extra["derivation"] = (
            extra.get("derivation")
            or "One JPEG from an arbitrary camera/DVR. Not a live NVR stream and not continuous YOLO."
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
