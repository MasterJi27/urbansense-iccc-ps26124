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
BACKEND_METRICS = ROOT / "backend" / "models" / "road_damage" / "metrics.json"
WEIGHTS = OUT_DIR / "YOLOv8_Small_RDD.pt"
INDIA_YAML = ROOT / ".data" / "rdd_india" / "data.yaml"
INDIA_BEST = OUT_DIR / "YOLOv8s_RDD_india.pt"

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # type: ignore[assignment]

CLASS_MAP = [
    {"id": "D00", "name": "Longitudinal crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D10", "name": "Transverse crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D20", "name": "Alligator crack", "maps_to": "ROAD_DAMAGE"},
    {"id": "D40", "name": "Pothole", "maps_to": "POTHOLE"},
]


def write_metrics(payload: dict) -> None:
    text = json.dumps(payload, indent=2)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(text, encoding="utf-8")
    BACKEND_METRICS.parent.mkdir(parents=True, exist_ok=True)
    BACKEND_METRICS.write_text(text, encoding="utf-8")
    print(f"wrote {METRICS}")


def _count_split(data: Path, split: str) -> int:
    root = data.parent
    folder = root / "images" / split
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})


def _eval_split(data: Path) -> str:
    return "test" if _count_split(data, "test") >= 20 else "val"


def _cuda() -> bool:
    return bool(torch is not None and torch.cuda.is_available())


def _per_class(box) -> dict[int, float]:
    """Per-class AP@0.5. Ultralytics box.maps is AP@0.5:0.95 — do not label that as map50."""
    out: dict[int, float] = {}
    if box is None:
        return out
    ap50 = getattr(box, "ap50", None)
    idx = getattr(box, "ap_class_index", None)
    if ap50 is None:
        return out
    try:
        values = [float(x) for x in list(ap50)]
    except Exception:
        return out
    if idx is None:
        for i, value in enumerate(values[:4]):
            out[i] = round(value, 4)
        return out
    try:
        indexes = [int(x) for x in list(idx)]
    except Exception:
        return out
    for i, cls in enumerate(indexes):
        if i < len(values):
            out[int(cls)] = round(values[i], 4)
    return out


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
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model", default=str(WEIGHTS) if WEIGHTS.is_file() else "yolov8s.pt")
    parser.add_argument("--device", default="")
    parser.add_argument("--eval-only", action="store_true", help="Val existing weights; do not train")
    parser.add_argument("--lr0", type=float, default=0.001)
    parser.add_argument("--freeze", type=int, default=10)
    args = parser.parse_args()
    if not args.data and INDIA_YAML.is_file():
        args.data = str(INDIA_YAML)
    if not args.data:
        return skip("No --data yaml. Run scripts/prepare_rdd_india.py first. Do not quote sivakanth/oracl4 mAP as UrbanSense.")
    data = Path(args.data)
    if not data.is_file():
        return skip(f"data yaml missing: {data}")
    if YOLO is None:
        return skip("ultralytics is not installed. pip install ultralytics in the training env.")

    device = args.device or ("0" if _cuda() else "cpu")
    model = YOLO(args.model)
    best = Path(args.model)
    if not args.eval_only:
        results = model.train(
            data=str(data),
            epochs=args.epochs,
            imgsz=args.imgsz,
            device=device,
            batch=8,
            workers=2,
            patience=20,
            lr0=args.lr0,
            lrf=0.01,
            freeze=args.freeze,
            copy_paste=0.2,
            close_mosaic=15,
            project=str(OUT_DIR / "runs"),
            name="india_v2",
            exist_ok=True,
        )
        save_dir = Path(getattr(results, "save_dir", OUT_DIR / "runs" / "india_v2"))
        best = save_dir / "weights" / "best.pt"
        if best.is_file():
            INDIA_BEST.write_bytes(best.read_bytes())
            print(f"copied {INDIA_BEST}")
    elif INDIA_BEST.is_file():
        best = INDIA_BEST
    split_name = _eval_split(data)
    metrics: dict = {}
    try:
        ev = model.val(data=str(data), imgsz=args.imgsz, device=device, split=split_name)
        box = getattr(ev, "box", None)
        metrics = {
            "map50": round(float(getattr(box, "map50", 0) or 0), 4) if box is not None else None,
            "map50_95": round(float(getattr(box, "map", 0) or 0), 4) if box is not None else None,
        }
        per = _per_class(box)
    except Exception as exc:
        return skip(f"Training finished but val failed: {exc}")

    classes = []
    for i, row in enumerate(CLASS_MAP):
        item = dict(row)
        if i in per:
            item["map50"] = per[i]
        item["index"] = i
        classes.append(item)

    write_metrics(
        {
            "honesty": "REAL" if metrics.get("map50") else "EXPERIMENTAL",
            "evaluated": bool(metrics.get("map50")),
            "dataset": "RDD2022 India (CRDDC) — this host",
            "note": (
                f"Held-out {split_name} after slow fine-tune (lr0={args.lr0}, freeze={args.freeze}). "
                "Not a certified field accuracy. Waterlogging and Indian signs were not trained. "
                "Do not quote a rival mAP as ours."
            ),
            "map50": metrics.get("map50"),
            "map50_95": metrics.get("map50_95"),
            "eval_split": split_name,
            "split": {
                "train": _count_split(data, "train"),
                "val": _count_split(data, "val"),
                "test": _count_split(data, "test"),
                "seed": 42,
                "keep": ["D00", "D10", "D20", "D40"],
            },
            "recipe": {"lr0": args.lr0, "freeze": args.freeze, "epochs": args.epochs, "d10_train_repeat": 10},
            "weights": "models/road_damage/YOLOv8s_RDD_india.pt" if INDIA_BEST.is_file() else str(best),
            "classes": classes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
