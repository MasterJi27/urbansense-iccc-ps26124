"""Demo/seed data — clearly separated from production business logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetCondition, AssetType, RoadSegment
from app.models.event import EventStatus, EventType, Severity, SourceType
from app.models.fleet import Bus, ProcessingMode, Route, SensorNode, Trip
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.schemas.common import ObservationIn
from app.security import hash_password
from app.services.observations import ingest_observation

DELHI = [
    (28.6139, 77.2090),
    (28.6165, 77.2150),
    (28.6200, 77.2220),
    (28.6240, 77.2280),
    (28.6280, 77.2340),
    (28.6320, 77.2400),
]

# Payload is SEED; engine is the capability that would run on a live still.
_ENGINE = {
    EventType.POTHOLE: "REAL",
    EventType.ROAD_DAMAGE: "REAL",
    EventType.ROAD_OBSTRUCTION: "REAL",
    EventType.WATERLOGGING: "SIMULATED",
    EventType.MISSING_ZEBRA: "RULE_BASED",
    EventType.DAMAGED_SIGN: "DISABLED",
    EventType.TRAFFIC_CONGESTION: "RULE_BASED",
    EventType.PEDESTRIAN_RISK: "RULE_BASED",
}


def _seed_extra(event_type: EventType, **more) -> dict:
    engine = _ENGINE.get(event_type, "RULE_BASED")
    return {
        "ai_status": "SIMULATED",
        "payload_kind": "SEED",
        "engine_status": engine,
        "derivation": f"Seed demo payload. Engine for {event_type.value} is {engine} (not a live still).",
        **more,
    }


def seed_if_empty(db: Session) -> None:
    if db.query(User).first():
        return
    seed(db)


def seed(db: Session) -> None:
    users = [
        User(
            email="superadmin@urbansense.local",
            full_name="Super Admin",
            hashed_password=hash_password("UrbanSense@2026"),
            role=UserRole.SUPER_ADMIN,
        ),
        User(
            email="admin@urbansense.local",
            full_name="City Admin",
            hashed_password=hash_password("UrbanSense@2026"),
            role=UserRole.ADMIN,
        ),
        User(
            email="inspector@urbansense.local",
            full_name="Field Inspector",
            hashed_password=hash_password("UrbanSense@2026"),
            role=UserRole.INSPECTOR,
        ),
        User(
            email="operator@urbansense.local",
            full_name="Bus Operator",
            hashed_password=hash_password("UrbanSense@2026"),
            role=UserRole.OPERATOR,
        ),
    ]
    db.add_all(users)
    db.flush()

    routes = []
    for i in range(1, 6):
        pts = DELHI + [(lat + 0.001 * i, lon + 0.001 * i) for lat, lon in DELHI]
        poly = ";".join(f"{lat},{lon}" for lat, lon in pts)
        routes.append(
            Route(
                code=f"RT-{i:02d}",
                name=f"Corridor {i}",
                planned_duration_minutes=40 + i * 3,
                simulated=True,
                polyline=poly,
            )
        )
    db.add_all(routes)
    db.flush()

    buses = []
    codes = [f"BUS-{i:03d}" for i in range(1, 9)] + ["BUS-017", "BUS-042"]
    for i, code in enumerate(codes):
        buses.append(
            Bus(
                code=code,
                registration=f"DL1PC{1000 + i}",
                route_id=routes[i % len(routes)].id,
                qr_payload=f"urbansense://bus/{code}",
            )
        )
    db.add_all(buses)
    db.flush()

    modes = [
        ProcessingMode.EDGE_AI,
        ProcessingMode.LIGHTWEIGHT_EDGE_AI,
        ProcessingMode.CAPTURE_AND_SENSOR,
        ProcessingMode.CLOUD_ASSISTED,
        ProcessingMode.EDGE_GATEWAY,
    ]
    sensors = []
    for i in range(5):
        sensors.append(
            SensorNode(
                code=f"NODE-{i + 1:03d}",
                bus_id=buses[i].id,
                device_label="PHONE" if i < 4 else "BUS_CCTV",
                source_type="PHONE" if i < 4 else "BUS_CCTV",
                processing_mode=modes[i],
                camera_status="ONLINE",
                gps_status="ONLINE",
                imu_status="ONLINE",
                battery_pct=80 - i * 8,
                network_type="4G",
                ai_mode="EDGE" if i == 0 else ("SIMULATION" if i < 4 else "EDGE_GATEWAY"),
                latitude=DELHI[i % len(DELHI)][0],
                longitude=DELHI[i % len(DELHI)][1],
            )
        )
    db.add_all(sensors)
    db.flush()

    asset_types = list(AssetType)
    assets = []
    for i in range(20):
        lat, lon = DELHI[i % len(DELHI)]
        at = asset_types[i % len(asset_types)]
        code = f"ASSET-{i + 1:03d}"
        assets.append(
            Asset(
                code=code,
                asset_type=at,
                name=f"{at.value.replace('_', ' ').title()} {i + 1}",
                latitude=lat + 0.0004 * i,
                longitude=lon + 0.0003 * i,
                qr_payload=f"urbansense://asset/{code}",
                condition=AssetCondition.FAIR if i % 3 else AssetCondition.POOR,
            )
        )
    db.add_all(assets)
    db.flush()

    # Bridges/Flyovers for SHM crowd — Delhi corridor real-ish coords snapped to seed map
    for code, atype, name, lat, lon, span, base in [
        ("BRG-ITO", AssetType.BRIDGE, "ITO Bridge — Yamuna", 28.6289, 77.2410, 180, 0.22),
        ("FLY-AIIMS", AssetType.FLYOVER, "AIIMS Flyover", 28.5670, 77.2100, 420, 0.28),
        ("BRG-DHAULA", AssetType.BRIDGE, "Dhaula Kuan Flyover", 28.5930, 77.1630, 260, 0.25),
    ]:
        db.add(
            Asset(
                code=code, asset_type=atype, name=name, latitude=lat, longitude=lon,
                qr_payload=f"urbansense://asset/{code}", condition=AssetCondition.FAIR,
                health_score=74 if code != "BRG-ITO" else 62, span_m=span, shm_baseline_rms=base, shm_last_rms=base, shm_anomaly_count=1 if code=="BRG-ITO" else 0,
            )
        )
    # Named expected-infrastructure assets for the GIS asset-watch demo.
    for code, atype, name, lat, lon in [
        ("SIGN-183", AssetType.TRAFFIC_SIGN, "Stop Sign 183", 28.6328, 77.2195),
        ("DIV-101", AssetType.DIVIDER, "Divider 101", 28.6240, 77.2280),
        ("ZEBRA-101", AssetType.ZEBRA_CROSSING, "Zebra Crossing 101", 28.6200, 77.2220),
    ]:
        db.add(
            Asset(
                code=code,
                asset_type=atype,
                name=name,
                latitude=lat,
                longitude=lon,
                qr_payload=f"urbansense://asset/{code}",
                condition=AssetCondition.GOOD,
            )
        )
    db.flush()

    segments = []
    for i in range(8):
        lat, lon = DELHI[i % len(DELHI)]
        segments.append(
            RoadSegment(
                code=f"SEG-{i + 1:02d}",
                name=f"Segment {i + 1} — Ring Road sample",
                latitude=lat,
                longitude=lon,
                traffic_exposure=80 + i * 20,
                pedestrian_exposure=20 + i * 8,
            )
        )
    db.add_all(segments)
    db.flush()
    db.commit()

    now = datetime.now(timezone.utc)
    types = [
        EventType.POTHOLE,
        EventType.ROAD_DAMAGE,
        EventType.WATERLOGGING,
        EventType.MISSING_ZEBRA,
        EventType.DAMAGED_SIGN,
        EventType.TRAFFIC_CONGESTION,
        EventType.PEDESTRIAN_RISK,
        EventType.ROAD_OBSTRUCTION,
    ]
    # ~50 observations; nearby pairs fuse.
    for i in range(40):
        lat, lon = DELHI[i % len(DELHI)]
        jitter = 0.00008 * (i % 3)
        bus = buses[i % 10]
        sensor = sensors[i % 5]
        ingest_observation(
            db,
            ObservationIn(
                event_type=types[i % len(types)],
                severity=Severity.HIGH if i % 5 == 0 else Severity.MEDIUM,
                latitude=lat + jitter,
                longitude=lon + jitter,
                gps_accuracy=4.5,
                timestamp=now - timedelta(minutes=i * 7),
                source_type=SourceType.DEMO,
                source_id=bus.code,
                sensor_id=sensor.id,
                bus_id=bus.id,
                route_id=bus.route_id,
                confidence=0.72 + (i % 10) * 0.02,
                simulated=True,
                extra=_seed_extra(types[i % len(types)]),
            ),
        )

    # Explicit fusion pair at Connaught-ish point for demo
    pothole_lat, pothole_lon = 28.6328, 77.2195
    ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.HIGH,
            latitude=pothole_lat,
            longitude=pothole_lon,
            gps_accuracy=3.2,
            timestamp=now - timedelta(minutes=12),
            source_type=SourceType.PHONE,
            source_id="BUS-042",
            sensor_id=sensors[0].id,
            bus_id=buses[0].id,
            confidence=0.82,
            simulated=True,
            extra=_seed_extra(EventType.POTHOLE, source_bus="BUS-042"),
        ),
    )
    ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.HIGH,
            latitude=pothole_lat + 0.00012,
            longitude=pothole_lon + 0.0001,
            gps_accuracy=5.0,
            timestamp=now - timedelta(minutes=8),
            source_type=SourceType.PHONE,
            source_id="BUS-017",
            sensor_id=sensors[1].id,
            bus_id=buses[1].id,
            confidence=0.89,
            simulated=True,
            extra=_seed_extra(EventType.POTHOLE, source_bus="BUS-017"),
        ),
    )
    ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.HIGH,
            latitude=pothole_lat + 0.00005,
            longitude=pothole_lon - 0.00004,
            gps_accuracy=2.0,
            timestamp=now - timedelta(minutes=3),
            source_type=SourceType.INSPECTOR,
            source_id="INSPECTOR",
            confidence=0.95,
            simulated=False,
            extra={
                "ai_status": "RULE_BASED",
                "payload_kind": "FIELD",
                "engine_status": "REAL",
                "derivation": "Inspector confirm. Phone trigger is RULE_BASED; YOLO RDD engine is REAL on stills.",
            },
        ),
    )

    # Seeded trips (flagged simulated) so OD + route-delay have demo rows.
    # Real fleet GPS would replace these without any schema change.
    for i in range(6):
        route = routes[i % len(routes)]
        bus = buses[i % len(buses)]
        start = now - timedelta(hours=3 - i * 0.4)
        actual = route.planned_duration_minutes + (4 if i % 2 else -2)
        db.add(
            Trip(
                bus_id=bus.id,
                sensor_id=sensors[i % len(sensors)].id,
                route_id=route.id,
                started_at=start,
                ended_at=start + timedelta(minutes=actual),
                actual_duration_minutes=actual,
                simulated=True,
            )
        )
    db.flush()

    # SHM demo events — ITO bridge anomalous vs AIIMS normal (crowd baseline visible)
    try:
        from app.services.bridge_shm import AccelSample, ingest_bridge_batch
        import math, random
        brg = db.query(Asset).filter(Asset.code == "BRG-ITO").first()
        if brg:
            base = 28.6289, 77.2410
            for k in range(3):
                samples = [AccelSample(t=i*0.02, ax=(random.random()-0.5)*0.3, ay=(random.random()-0.5)*0.3, az=(random.random()-0.5)*1.1) for i in range(180)]
                ingest_bridge_batch(db, samples, base[0]+k*0.00006, base[1], 4.0, 28, SourceType.PHONE, f"BUS-04{k}", sensors[k%5].id, buses[k].id, buses[k].route_id, simulated=True)
            # one normal baseline for AIIMS
            samples = [AccelSample(t=i*0.02, ax=(random.random()-0.5)*0.15, ay=(random.random()-0.5)*0.15, az=(random.random()-0.5)*0.5) for i in range(160)]
            ingest_bridge_batch(db, samples, 28.5670, 77.2100, 5.0, 32, SourceType.PHONE, "BUS-017", sensors[1].id, buses[1].id, buses[1].route_id, simulated=True)
    except Exception:
        pass

    events = db.query(__import__("app.models.event", fromlist=["UrbanEvent"]).UrbanEvent).all()
    inspector = db.query(User).filter(User.email == "inspector@urbansense.local").first()
    for i, ev in enumerate(events[:10]):
        code = f"WO-{i + 1:03d}"
        db.add(
            WorkOrder(
                public_code=code,
                event_id=ev.id,
                title=f"Repair {ev.event_type.value} at {ev.public_code}",
                description="Seeded work order for demo.",
                status=WorkOrderStatus.PENDING if i > 2 else WorkOrderStatus.ASSIGNED,
                assignee_id=inspector.id if inspector and i <= 2 else None,
                qr_payload=f"urbansense://work-order/{code}",
            )
        )
        if i == 0:
            ev.status = EventStatus.ASSIGNED
    db.commit()
    ensure_camera_bays(db)


def ensure_camera_bays(db: Session) -> None:
    """PS 26124: front/rear/side/cabin bays on demo buses. Idempotent."""
    from app.services.ps26124 import CAMERA_BAYS

    for code in ("BUS-042", "BUS-017"):
        bus = db.query(Bus).filter(Bus.code == code).first()
        if not bus:
            continue
        for bay in CAMERA_BAYS:
            node_code = f"{code}-{bay}"
            if db.query(SensorNode).filter(SensorNode.code == node_code).first():
                continue
            db.add(
                SensorNode(
                    code=node_code,
                    bus_id=bus.id,
                    device_label=f"BUS_CCTV_{bay}",
                    source_type="BUS_CCTV",
                    processing_mode=ProcessingMode.EDGE_AI if bay != "CABIN" else ProcessingMode.LIGHTWEIGHT_EDGE_AI,
                    camera_status="ONLINE",
                    gps_status="ONLINE",
                    imu_status="ONLINE" if bay == "FRONT" else "UNAVAILABLE",
                    battery_pct=92,
                    network_type="4G",
                    ai_mode="EDGE",
                    latitude=28.6328,
                    longitude=77.2195,
                )
            )
    db.commit()
