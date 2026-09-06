"""Azure-hosted RDD YOLO (ONNX CPU). Phone/CCTV stills hit this — not the officer laptop."""

from __future__ import annotations

import io
import time
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

try:
    import numpy as np
    import onnxruntime as ort
    from PIL import Image
except ImportError:
    np = None  # type: ignore[assignment]
    ort = None  # type: ignore[assignment]
    Image = None  # type: ignore[assignment]

from app.models.event import EventType, Severity

CLASSES = [
    {"id": "D00", "name": "Longitudinal crack", "event_type": EventType.ROAD_DAMAGE, "severity": Severity.MEDIUM},
    {"id": "D10", "name": "Transverse crack", "event_type": EventType.ROAD_DAMAGE, "severity": Severity.MEDIUM},
    {"id": "D20", "name": "Alligator crack", "event_type": EventType.ROAD_DAMAGE, "severity": Severity.HIGH},
    {"id": "D40", "name": "Pothole", "event_type": EventType.POTHOLE, "severity": Severity.HIGH},
]
IMGSZ = 640
CONF = 0.18
IOU = 0.45
_LOCK = Lock()


def weights_path() -> Path:
    here = Path(__file__).resolve()
    return here.parents[1] / "weights" / "rdd_india.onnx"


def rdd_cloud_status() -> dict[str, Any]:
    path = weights_path()
    ready = path.is_file() and path.stat().st_size > 1_000_000 and ort is not None and np is not None
    honesty = "REAL" if ready else "DISABLED"
    return {
        "honesty": honesty,
        "ai_status": honesty,
        "evaluated": ready,
        "provider": "Azure App Service",
        "runtime": "onnxruntime-cpu",
        "model": "YOLOv8s RDD India",
        "weights": str(path.name),
        "note": (
            "Cloud still inference on this App Service. Not a 24×7 GPU stream. Cabin bay still cannot invent a road defect."
            if ready
            else "rdd_india.onnx or onnxruntime missing on this host."
        ),
    }


def warmup_rdd() -> None:
    if rdd_cloud_status()["evaluated"]:
        _session()


@lru_cache(maxsize=1)
def _session():
    if ort is None or np is None:
        return None
    path = weights_path()
    if not path.is_file():
        return None
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


def _letterbox(image: Any) -> tuple[Any, float, int, int]:
    w, h = image.size
    scale = min(IMGSZ / w, IMGSZ / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = image.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (IMGSZ, IMGSZ), (114, 114, 114))
    pad_x = (IMGSZ - nw) // 2
    pad_y = (IMGSZ - nh) // 2
    canvas.paste(resized, (pad_x, pad_y))
    return canvas, scale, pad_x, pad_y


def _nms(boxes: Any, scores: Any) -> list[int]:
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-9)
        order = rest[iou < IOU]
    return keep


def _xywh_to_xyxy(raw: Any) -> Any:
    x, y, w, h = raw[:, 0], raw[:, 1], raw[:, 2], raw[:, 3]
    return np.stack([x - w / 2, y - h / 2, x + w / 2, y + h / 2], axis=1)


def detect_rdd(data: bytes, *, conf: float = CONF) -> dict[str, Any]:
    status = rdd_cloud_status()
    empty = {"ok": False, "ai_status": status["honesty"], "detections": [], "model": status["model"], "provider": status["provider"]}
    if not status["evaluated"] or Image is None or np is None:
        empty["reason"] = status["note"]
        return empty
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        empty["reason"] = f"unreadable still: {exc}"
        return empty
    orig_w, orig_h = image.size
    canvas, scale, pad_x, pad_y = _letterbox(image)
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = np.transpose(arr, (2, 0, 1))[None, ...]
    t0 = time.perf_counter()
    try:
        with _LOCK:
            sess = _session()
            if sess is None:
                empty["reason"] = "onnx session failed"
                return empty
            inp = sess.get_inputs()[0].name
            raw = sess.run(None, {inp: tensor})[0]
    except Exception as exc:
        empty["reason"] = str(exc)
        return empty
    infer_ms = int(round((time.perf_counter() - t0) * 1000))

    detections = _decode(raw, orig_w, orig_h, scale, pad_x, pad_y, conf)
    return {
        "ok": True,
        "ai_status": "REAL" if detections else "REAL",
        "engine_status": "REAL",
        "provider": "Azure App Service",
        "model": "YOLOv8s_RDD_india.onnx",
        "runtime": "onnxruntime-cpu",
        "detections": detections,
        "count": len(detections),
        "infer_ms": infer_ms,
        "note": "India RDD on this still. App Service CPU, not a GPU stream. Typical 0.3–1.2 s plus Vision.",
    }


def _decode(raw: Any, orig_w: int, orig_h: int, scale: float, pad_x: int, pad_y: int, conf: float) -> list[dict[str, Any]]:
    out = np.array(raw)
    if out.ndim == 3:
        out = out[0]
    if out.shape[0] < out.shape[-1] and out.shape[0] <= 16:
        out = out.T
    if out.shape[1] < 6:
        return []
    boxes = _xywh_to_xyxy(out[:, :4])
    cls_scores = out[:, 4:]
    cls_ids = cls_scores.argmax(axis=1)
    scores = cls_scores.max(axis=1)
    mask = scores >= conf
    boxes, scores, cls_ids = boxes[mask], scores[mask], cls_ids[mask]
    keep = _nms(boxes, scores)
    dets: list[dict[str, Any]] = []
    for i in keep[:20]:
        idx = int(cls_ids[i])
        if idx < 0 or idx >= len(CLASSES):
            continue
        x1, y1, x2, y2 = boxes[i]
        nx1 = max(0.0, min(1.0, ((x1 - pad_x) / scale) / orig_w))
        ny1 = max(0.0, min(1.0, ((y1 - pad_y) / scale) / orig_h))
        nx2 = max(0.0, min(1.0, ((x2 - pad_x) / scale) / orig_w))
        ny2 = max(0.0, min(1.0, ((y2 - pad_y) / scale) / orig_h))
        if nx2 - nx1 <= 0 or ny2 - ny1 <= 0:
            continue
        meta = CLASSES[idx]
        dets.append(
            {
                "klass": meta["name"],
                "class_id": meta["id"],
                "confidence": round(float(scores[i]), 4),
                "bbox": [round(float(nx1), 4), round(float(ny1), 4), round(float(nx2), 4), round(float(ny2), 4)],
                "event_type": meta["event_type"].value,
                "severity": meta["severity"].value,
            }
        )
    dets.sort(key=lambda row: row["confidence"], reverse=True)
    return dets


def top_event(detections: list[dict[str, Any]]) -> dict[str, Any] | None:
    return detections[0] if detections else None
