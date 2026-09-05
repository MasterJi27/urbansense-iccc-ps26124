"""RULE_BASED municipal routing. Not a learned dispatcher."""

from __future__ import annotations

from app.models.event import EventType
from app.persist import write_extra

# code, desk label, note
_ROUTES: dict[EventType, tuple[str, str, str]] = {
    EventType.POTHOLE: ("PWD_ROADS", "PWD — Roads", "Ward roads cell. Area/severity is a separate rule."),
    EventType.ROAD_DAMAGE: ("PWD_ROADS", "PWD — Roads", "Cracks / alligator / patch. Same desk as potholes."),
    EventType.WATERLOGGING: ("WATER_CELL", "Water / flood cell", "No flood neural net. Human or seed tap only."),
    EventType.MISSING_DIVIDER: ("PWD_TRAFFIC_CIVIL", "PWD — Traffic civil", "GIS absence, not a detector."),
    EventType.MISSING_ZEBRA: ("PWD_TRAFFIC_CIVIL", "PWD — Traffic civil", "GIS absence, not a detector."),
    EventType.DAMAGED_SIGN: ("TRAFFIC_SIGNS", "Traffic signs", "Indian sign net is DISABLED. GIS pass only."),
    EventType.ROAD_OBSTRUCTION: ("PWD_ROADS", "PWD — Roads", "Hazard / blockage desk."),
    EventType.TRAFFIC_CONGESTION: ("TRAFFIC_POLICE", "Traffic police assist", "LOS rule, not a forecast model."),
    EventType.PEDESTRIAN_RISK: ("TRAFFIC_VRU", "VRU / school cell", "BBox proximity. Not a child classifier."),
    EventType.SCHOOL_CROSSING: ("TRAFFIC_VRU", "VRU / school cell", "Geofence + person/vehicle proximity."),
    EventType.HIT_AND_RUN: ("TRAFFIC_POLICE", "Traffic police assist", "Track + plate. Does not accuse."),
    EventType.RASH_DRIVING: ("TRAFFIC_POLICE", "Traffic police assist", "Speed heuristic. Does not accuse."),
    EventType.VEHICLE: ("TRAFFIC_POLICE", "Traffic police assist", "COCO vehicle count / density."),
    EventType.PEDESTRIAN: ("TRAFFIC_VRU", "VRU / school cell", "Person box only."),
    EventType.BRIDGE_VIBRATION: ("PWD_BRIDGE", "PWD — Bridge cell", "Phone IMU crowd, not collapse prediction."),
    EventType.FLYOVER_JOINT: ("PWD_BRIDGE", "PWD — Bridge cell", "Joint / IMU cluster."),
    EventType.BRIDGE_ANOMALY: ("PWD_BRIDGE", "PWD — Bridge cell", "Citizen QR or IMU anomaly."),
    EventType.OTHER: ("ICCC_TRIAGE", "ICCC triage", "Unclassified still. Officer labels it."),
}


def department_for(event_type: EventType | str) -> dict:
    key = event_type if isinstance(event_type, EventType) else EventType(event_type)
    code, desk, note = _ROUTES.get(key, _ROUTES[EventType.OTHER])
    return {
        "department_code": code,
        "department_desk": desk,
        "department_note": note,
        "department_honesty": "RULE_BASED",
    }


def attach_department(event) -> None:
    extra = dict(event.extra or {})
    extra.update(department_for(event.event_type))
    write_extra(event, extra)
