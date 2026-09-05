"""BEL PS 26124 coverage — jury-facing, honest. Not a claim of live city SOC."""

from __future__ import annotations

from app.models.event import EventType

CAMERA_BAYS = ("FRONT", "REAR", "LEFT", "RIGHT", "CABIN")
ROAD_TYPES = {
    EventType.POTHOLE,
    EventType.ROAD_DAMAGE,
    EventType.WATERLOGGING,
    EventType.MISSING_DIVIDER,
    EventType.MISSING_ZEBRA,
    EventType.DAMAGED_SIGN,
    EventType.ROAD_OBSTRUCTION,
    EventType.TRAFFIC_CONGESTION,
}

COVERAGE = [
    {"id": "potholes", "requirement": "Potholes", "status": "REAL", "how": "RDD YOLO on road stills / Azure Vision tags on phone stills"},
    {"id": "damaged_roads", "requirement": "Damaged roads", "status": "REAL", "how": "Same RDD crack classes → ROAD_DAMAGE"},
    {"id": "missing_dividers", "requirement": "Missing dividers", "status": "RULE_BASED", "how": "GIS asset-watch, not neural absence"},
    {"id": "missing_zebra", "requirement": "Missing zebra crossings", "status": "RULE_BASED", "how": "GIS asset-watch, not neural absence"},
    {"id": "signs", "requirement": "Damaged/missing signboards", "status": "DISABLED", "how": "Turkish sign weights off; GIS pass only"},
    {"id": "waterlogging", "requirement": "Waterlogging", "status": "SIMULATED", "how": "No dedicated waterlogging net. Azure flood tag is mapping only"},
    {"id": "hazards", "requirement": "Other road hazards", "status": "REAL", "how": "ROAD_OBSTRUCTION + work-order loop"},
    {"id": "vehicles", "requirement": "Vehicle detect / class / count / density", "status": "REAL", "how": "YOLOv8 COCO + ByteTrack; density is LOS rule"},
    {"id": "bottlenecks", "requirement": "Traffic bottlenecks", "status": "RULE_BASED", "how": "LOS E/F persistence, not a traffic-forecast model"},
    {"id": "vru", "requirement": "Vulnerable pedestrians / school crossing", "status": "RULE_BASED", "how": "BBox proximity + school geofence. Not a child detector"},
    {"id": "hit_run", "requirement": "Hit-and-run / rash driving", "status": "RULE_BASED", "how": "Speed heuristic + track + ANPR. No accident classifier"},
    {"id": "anpr", "requirement": "Plate + confidence + time + GPS", "status": "REAL", "how": "ANPR on still; plate masked until ADMIN/INSPECTOR"},
    {"id": "central", "requirement": "Secure central alerts", "status": "REAL", "how": "JWT + WebSocket event.created"},
    {"id": "fleet", "requirement": "Fleet aggregation", "status": "REAL", "how": "Buses, five camera bays, heartbeats"},
    {"id": "gis", "requirement": "GIS map + congestion heatmap", "status": "REAL", "how": "Leaflet + /analytics/heatmap"},
    {"id": "infra", "requirement": "Infrastructure deficiencies", "status": "RULE_BASED", "how": "Asset passport + road-health score"},
    {"id": "od", "requirement": "OD patterns + route delays", "status": "SIMULATED", "how": "Seeded trips; empty when no real AVL"},
    {"id": "actions", "requirement": "Actionable insights / work orders", "status": "REAL", "how": "Verify → WO → repair → re-verify"},
    {"id": "edge", "requirement": "Edge-AI + low bandwidth", "status": "REAL", "how": "Onboard stills, ~1KB JSON, no video upload"},
    {"id": "multicam", "requirement": "Front / rear / side / cabin cameras", "status": "REAL", "how": "Five bays. Cabin never scores road defects. Frames, not raw video to cloud"},
]


def apply_camera_bay(event_type: EventType, bay: str | None) -> tuple[EventType, str | None]:
    slot = (bay or "FRONT").upper()
    if slot not in CAMERA_BAYS:
        slot = "FRONT"
    if slot == "CABIN" and event_type in ROAD_TYPES:
        return EventType.OTHER, "Cabin camera does not score road defects (PS 26124 cabin vs road split)."
    return event_type, None


def coverage_payload() -> dict:
    counts: dict[str, int] = {}
    for row in COVERAGE:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "problem_statement": "26124",
        "org": "Bharat Electronics Limited",
        "title": "AI-Powered Mobile Urban Intelligence Platform Using Public Transport Fleet",
        "note": "Edge analyses sampled frames from bus camera bays. Cloud stores alerts, not continuous video.",
        "counts": counts,
        "items": COVERAGE,
        "camera_bays": list(CAMERA_BAYS),
    }
