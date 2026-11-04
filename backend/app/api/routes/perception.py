from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.event import EventType, SourceType
from app.models.user import User
from app.schemas.common import ObservationIn
from app.services.azure_edge import (
    StillRejected,
    azure_openai_status,
    azure_safety_status,
    azure_stack_status,
    azure_vision_status,
    read_still,
)
from app.services.bbox_severity import severity_for_detection
from app.services.composio_notify import composio_status
from app.services.model_metrics import load_model_metrics
from app.services.observations import ingest_observation, publish_event, save_evidence_bytes
from app.services.ps26124 import apply_camera_bay, coverage_payload
from app.services.rdd_cloud import detect_rdd, rdd_cloud_status, top_event

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/ps26124")
def ps26124(_: User = Depends(get_current_user)):
    return coverage_payload()


@router.get("/capabilities")
def capabilities(_: User = Depends(get_current_user)):
    rdd = rdd_cloud_status()
    return {
        "available": rdd.get("honesty") == "REAL",
        "road_damage": rdd,
        "azure_vision": azure_vision_status(),
        "azure_openai": azure_openai_status(),
        "azure_content_safety": azure_safety_status(),
        "azure_stack": azure_stack_status(),
        "rdd_eval": load_model_metrics(),
        "composio": composio_status(),
        "note": "RDD confirm runs on this App Service from stills. Windshield boxes are on-device preview.",
    }


@router.post("/analyze-frame")
async def analyze_frame(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    latitude: float = Form(28.6328),
    longitude: float = Form(77.2195),
    source_id: str = Form("WEBCAM-01"),
    source_type: str = Form("PHONE"),
    camera_bay: str = Form("FRONT"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = await read_still(file)
    except StillRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    name = file.filename or "frame.jpg"
    try:
        url = await run_in_threadpool(save_evidence_bytes, name, data)
    except Exception as exc:
        return {"ok": False, "error": f"evidence store failed: {exc}"}
    rdd = await run_in_threadpool(detect_rdd, data)
    detections = rdd.get("detections") or []
    top = top_event(detections)
    if top is None:
        return {
            "ok": True,
            "evidence_url": url,
            "count": 0,
            "items": [],
            "detections": [],
            "rdd": rdd,
            "capabilities": {"road_damage": rdd_cloud_status()},
        }
    extra = {
        "method": "azure-rdd-onnx",
        "model": rdd.get("model"),
        "ai_status": "REAL",
        "engine_status": "REAL",
        "patrol": True,
        "camera_bay": (camera_bay or "FRONT").upper(),
        "rdd": rdd,
        "detections": detections,
        "derivation": "Azure-hosted RDD YOLO. Same engine as /ingest/phone/still.",
    }
    graded = severity_for_detection(top)
    extra["bbox_severity"] = {k: (v.value if hasattr(v, "value") else v) for k, v in graded.items()}
    extra["severity_honesty"] = "RULE_BASED"
    sev = graded["severity"]
    typed, note = apply_camera_bay(EventType(top["event_type"]), camera_bay)
    if note:
        extra["derivation"] = note
    obs_in = ObservationIn(
        event_type=typed,
        severity=sev,
        latitude=latitude,
        longitude=longitude,
        source_type=SourceType(source_type) if not isinstance(source_type, SourceType) else source_type,
        source_id=source_id,
        confidence=float(top["confidence"]),
        simulated=False,
        evidence_url=url,
        extra=extra,
    )
    obs, event, created = await run_in_threadpool(ingest_observation, db, obs_in, actor_id=user.id)
    background.add_task(publish_event, event, created)
    return {
        "ok": True,
        "evidence_url": url,
        "count": 1,
        "items": [{"event": event.public_code, "type": event.event_type.value, "created": created, "simulated": obs.simulated}],
        "detections": detections,
        "rdd": rdd,
        "capabilities": {"road_damage": rdd_cloud_status()},
    }
