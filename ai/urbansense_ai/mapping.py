"""Map detector class names onto UrbanSense EventType. Severity ≠ model confidence."""

from __future__ import annotations

RDD_TO_EVENT = {
    "potholes": ("POTHOLE", "HIGH"),
    "pothole": ("POTHOLE", "HIGH"),
    "longitudinal crack": ("ROAD_DAMAGE", "MEDIUM"),
    "transverse crack": ("ROAD_DAMAGE", "MEDIUM"),
    "alligator crack": ("ROAD_DAMAGE", "HIGH"),
}

COCO_VEHICLE = {"car", "motorcycle", "bus", "truck", "bicycle"}
COCO_PERSON = {"person"}


def rdd_event(label: str) -> tuple[str, str]:
    return RDD_TO_EVENT.get(label.strip().lower(), ("ROAD_DAMAGE", "MEDIUM"))


def vehicle_event(label: str) -> str:
    if label.lower() in COCO_PERSON:
        return "PEDESTRIAN"
    return "VEHICLE"
