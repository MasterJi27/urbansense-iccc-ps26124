"""Export the India RDD weights to ONNX for Azure CPU (no PyTorch on App Service)."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_CANDIDATES = [
    ROOT / "models" / "road_damage" / "YOLOv8s_RDD_india.pt",
    ROOT / "models" / "road_damage" / "YOLOv8_Small_RDD.pt",
]
DEST = ROOT / "backend" / "app" / "weights" / "rdd_india.onnx"


def main() -> int:
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics missing — run from .venv-train", file=sys.stderr)
        return 2
    src = next((p for p in SRC_CANDIDATES if p.is_file() and p.stat().st_size > 1_000_000), None)
    if src is None:
        print("no RDD .pt to export", file=sys.stderr)
        return 2
    model = YOLO(str(src))
    out = Path(model.export(format="onnx", imgsz=640, simplify=True, opset=12, nms=False))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, DEST)
    print(f"exported {src.name} -> {DEST} ({DEST.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
