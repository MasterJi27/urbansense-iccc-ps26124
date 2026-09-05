from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"

RDD_URL = "https://github.com/oracl4/RoadDamageDetection/raw/main/models/YOLOv8_Small_RDD.pt"
RDD_PATH = MODELS / "road_damage" / "YOLOv8_Small_RDD.pt"
COCO_PATH = MODELS / "traffic" / "yolov8n.pt"
SIGN_PATH = MODELS / "traffic_sign" / "best.pt"
PLATE_PATH = MODELS / "anpr" / "plate.pt"


def ensure_dir(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def download(url: str, dest: Path) -> Path:
    ensure_dir(dest)
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    import urllib.request

    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(dest)
    return dest


def resolve_rdd() -> Path | None:
    env = os.environ.get("URBANSENSE_RDD_WEIGHTS")
    if env and Path(env).exists():
        return Path(env)
    if RDD_PATH.exists():
        return RDD_PATH
    try:
        return download(RDD_URL, RDD_PATH)
    except Exception:
        return RDD_PATH if RDD_PATH.exists() else None


def resolve_coco() -> str:
    env = os.environ.get("URBANSENSE_VEHICLE_WEIGHTS")
    if env:
        return env
    ensure_dir(COCO_PATH)
    if COCO_PATH.exists():
        return str(COCO_PATH)
    # Ultralytics downloads bare "yolov8n.pt" into the process CWD on first
    # use; migrate a stray root-level download into models/traffic/.
    stray = ROOT / "yolov8n.pt"
    if stray.exists() and stray.stat().st_size > 1_000_000:
        try:
            ensure_dir(COCO_PATH)
            stray.replace(COCO_PATH)
            return str(COCO_PATH)
        except OSError:
            return str(stray)
    return str(COCO_PATH) if COCO_PATH.exists() else "yolov8n.pt"


def resolve_signs() -> Path | None:
    env = os.environ.get("URBANSENSE_SIGN_WEIGHTS")
    if env and Path(env).exists():
        return Path(env)
    if SIGN_PATH.exists():
        return SIGN_PATH
    nested = ROOT / "boost" / "TrafficSignRecognition-master" / "TrafficSignRecognition-master" / "yolov5_model" / "weights" / "best.pt"
    return nested if nested.exists() else None


def resolve_plate() -> Path | None:
    env = os.environ.get("URBANSENSE_PLATE_WEIGHTS")
    if env and Path(env).exists():
        return Path(env)
    return PLATE_PATH if PLATE_PATH.exists() else None
