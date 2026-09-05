from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.event import EventType
from app.models.user import User
from app.schemas.common import ObservationIn
from app.services.azure_edge import azure_openai_status, azure_safety_status, azure_stack_status, azure_vision_status
from app.services.observations import ingest_observation, publish_event, save_evidence_bytes
from app.services.ps26124 import apply_camera_bay, coverage_payload

router = APIRouter(prefix="/ai", tags=["ai"])

_AI_ROOT = Path(__file__).resolve().parents[4] / "ai"
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))


@router.get("/ps26124")
def ps26124(_: User = Depends(get_current_user)):
    return coverage_payload()


@router.get("/capabilities")
def capabilities(_: User = Depends(get_current_user)):
    try:
        from urbansense_ai.pipeline import PerceptionPipeline

        caps = PerceptionPipeline().capabilities()
        caps["azure_vision"] = azure_vision_status()
        caps["azure_openai"] = azure_openai_status()
        caps["azure_content_safety"] = azure_safety_status()
        caps["azure_stack"] = azure_stack_status()
        return caps
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
            "hint": "pip install -r ai/requirements-ai.txt then run python -m urbansense_ai.run_camera",
            "azure_vision": azure_vision_status(),
            "azure_openai": azure_openai_status(),
            "azure_content_safety": azure_safety_status(),
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
    data = await file.read()
    name = file.filename or "frame.jpg"
    url = save_evidence_bytes(name, data)
    try:
        import cv2
        import numpy as np
        from urbansense_ai.pipeline import FrameContext, PerceptionPipeline

        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"ok": False, "evidence_url": url, "error": "unreadable image"}
        pipe = PerceptionPipeline()
        payloads = pipe.process(frame, FrameContext(latitude=latitude, longitude=longitude, source_id=source_id, source_type=source_type))
    except Exception as exc:
        return {"ok": False, "evidence_url": url, "error": str(exc), "capabilities_hint": "/ai/capabilities"}

    results = []
    for body in payloads:
        body["evidence_url"] = url
        extra = dict(body.get("extra") or {})
        extra["camera_bay"] = (camera_bay or "FRONT").upper()
        raw_type = body.get("event_type")
        if raw_type:
            typed, note = apply_camera_bay(EventType(raw_type), camera_bay)
            body["event_type"] = typed.value
            if note:
                extra["derivation"] = note
        body["extra"] = extra
        obs_in = ObservationIn(**{k: v for k, v in body.items() if k in ObservationIn.model_fields})
        obs, event, created = ingest_observation(db, obs_in, actor_id=user.id)
        background.add_task(publish_event, event, created)
        results.append({"event": event.public_code, "type": event.event_type.value, "created": created, "simulated": obs.simulated})
    return {"ok": True, "evidence_url": url, "count": len(results), "items": results, "capabilities": pipe.capabilities()}
