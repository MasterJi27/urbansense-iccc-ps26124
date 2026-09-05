"""Fine-tune YOLOv8 on RDD2022 India. Writes models/road_damage/metrics.json.

Honesty: this script does not invent mAP. If Ultralytics or the dataset is missing
it exits with EXPERIMENTAL / evaluated=false. Classes stay D00/D10/D20/D40.

  python scripts/train_rdd.py --data path/to/rdd_india.yaml --epochs 50

Dataset: https://doi.org/10.6084/m9.figshare.21431547 (RDD2022 / CRDDC).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "models" / "road_damage"
METRICS = OUT_DIR / "metrics.json"
WEIGHTS = OUT_DIR / "YOLOv8_Small_RDD.pt"

CLASS_MAP = [
    {"id": "D00", "name": "Longitudinal crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D10", "name": "Transverse crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D20", "name": "Alligator crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D40", "name": "Pothole", "maps_to": "POTHOLE"},
]


def write_metrics(payload: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {METRICS}")


def skip(reason: str) -> int:
    write_metrics(
        {
            "honesty": "EXPERIMENTAL",
            "evaluated": False,
            "dataset": "RDD2022 India (CRDDC)",
            "note": reason,
            "classes": CLASS_MAP,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    print(reason, file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Honest RDD2022 India fine-tune")
    parser.add_argument("--data", help="Ultralytics data yaml (train/val + names D00 D10 D20 D40)")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model", default=str(WEIGHTS) if WEIGHTS.is_file() else "yolov8s.pt")
    parser.add_argument("--device", default="")
    args = parser.parse_args()
    if not args.data:
        return skip("No --data yaml. Download RDD2022 India, convert VOC→YOLO, then re-run. Do not quote sivakanth/oracl4 mAP as UrbanSense.")
    data = Path(args.data)
    if not data.is_file():
        return skip(f"data yaml missing: {data}")
    try:
        from ultralytics import YOLO
    except ImportError:
        return skip("ultralytics is not installed. pip install ultralytics in the training env.")

    model = YOLO(args.model)
    results = model.train(data=str(data), epochs=args.epochs, imgsz=args.imgsz, device=args.device or None, project=str(OUT_DIR / "runs"), name="india")
    best = Path(getattr(results, "save_dir", OUT_DIR)) / "weights" / "best.pt"
    metrics = {}
    try:
        ev = model.val(data=str(data), imgsz=args.imgsz)
        box = getattr(ev, "box", None)
        metrics = {
            "map50": float(getattr(box, "map50", 0) or 0) if box is not None else None,
            "map50_95": float(getattr(box, "map", 0) or 0) if box is not None else None,
        }
    except Exception as exc:
        return skip(f"Training finished but val failed: {exc}")

    classes = []
    for i, row in enumerate(CLASS_MAP):
        item = dict(row)
        if metrics.get("map50") is not None:
            item["map50"] = "see overall — per-class in Ultralytics val"
        item["index"] = i
        classes.append(item)

    write_metrics(
        {
            "honesty": "REAL" if metrics.get("map50") else "EXPERIMENTAL",
            "evaluated": bool(metrics.get("map50")),
            "dataset": "RDD2022 India (CRDDC) — this host",
            "note": "Our val split only. Not a certified field accuracy. Waterlogging and Indian signs were not trained.",
            "map50": metrics.get("map50"),
            "map50_95": metrics.get("map50_95"),
            "weights": str(best) if best.is_file() else args.model,
            "classes": classes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
