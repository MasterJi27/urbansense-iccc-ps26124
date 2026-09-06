"""Export windshield RDD ONNX. Person net stays off on /field."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RDD_PT = [
    ROOT / "models" / "road_damage" / "YOLOv8s_RDD_india.pt",
    ROOT / "models" / "road_damage" / "YOLOv8_Small_RDD.pt",
]
CLOUD_RDD = ROOT / "backend" / "app" / "weights" / "rdd_india.onnx"
DEST_DIR = ROOT / "dashboard" / "public" / "weights"
RDD_WEB = DEST_DIR / "rdd_web.onnx"
MANIFEST = DEST_DIR / "manifest.json"

RDD_CLASSES = [
    {"id": "D00", "name": "Longitudinal crack", "event_type": "ROAD_DAMAGE"},
    {"id": "D10", "name": "Transverse crack", "event_type": "ROAD_DAMAGE"},
    {"id": "D20", "name": "Alligator crack", "event_type": "ROAD_DAMAGE"},
    {"id": "D40", "name": "Pothole", "event_type": "POTHOLE"},
]


def _export(src: Path, dest: Path, imgsz: int) -> bool:
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics missing — skip export", file=sys.stderr)
        return False
    model = YOLO(str(src))
    out = Path(model.export(format="onnx", imgsz=imgsz, simplify=True, opset=12, nms=False))
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, dest)
    print(f"exported {src.name} imgsz={imgsz} -> {dest} ({dest.stat().st_size} bytes)")
    return True


def main() -> int:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    rdd_size = 640
    pt = next((p for p in RDD_PT if p.is_file() and p.stat().st_size > 1_000_000), None)
    if pt and _export(pt, RDD_WEB, 640):
        rdd_size = 640
    elif CLOUD_RDD.is_file():
        shutil.copy2(CLOUD_RDD, RDD_WEB)
        rdd_size = 640
        print(f"copied cloud RDD {CLOUD_RDD.name} -> {RDD_WEB} (imgsz=640 fallback)")
    else:
        print("no RDD weights to publish", file=sys.stderr)
        return 2

    manifest = {
        "rdd": {
            "file": "rdd_web.onnx",
            "imgsz": rdd_size,
            "honesty": "on-device preview of India RDD family — not a new test mAP",
            "classes": RDD_CLASSES,
        },
        "person": {
            "file": None,
            "imgsz": 320,
            "honesty": "Person detector is disabled on the field overlay. Road RDD only.",
            "enabled": False,
        },
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
