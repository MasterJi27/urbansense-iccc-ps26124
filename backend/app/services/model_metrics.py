"""Read a local RDD eval file. Never invent mAP."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings

_DEFAULT = {
    "honesty": "EXPERIMENTAL",
    "evaluated": False,
    "dataset": "RDD2022 India (CRDDC) — not run on this host",
    "note": "No models/road_damage/metrics.json. Train with scripts/train_rdd.py. Do not quote a rival mAP as ours.",
    "classes": [
        {"id": "D00", "name": "Longitudinal crack", "maps_to": "ROAD_DAMAGE"},
        {"id": "D10", "name": "Transverse crack", "maps_to": "ROAD_DAMAGE"},
        {"id": "D20", "name": "Alligator crack", "maps_to": "ROAD_DAMAGE"},
        {"id": "D40", "name": "Pothole", "maps_to": "POTHOLE"},
    ],
}


def metrics_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "models" / "road_damage" / "metrics.json"


def load_model_metrics() -> dict:
    path = metrics_path()
    if not path.is_file():
        return dict(_DEFAULT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        out = dict(_DEFAULT)
        out["note"] = "metrics.json exists but is not valid JSON."
        return out
    if not isinstance(data, dict):
        return dict(_DEFAULT)
    data.setdefault("honesty", "EXPERIMENTAL")
    data.setdefault("evaluated", True)
    data.setdefault("weights", get_settings().app_name)
    return data
