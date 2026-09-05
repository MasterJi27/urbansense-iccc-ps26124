from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import require_roles
from app.models.asset import Asset, AssetCondition, AssetType
from app.models.event import EventStatus, EventType, Severity, SourceType, UrbanEvent
from app.models.fleet import Bus, SensorNode
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.schemas.common import ObservationIn
from app.persist import write_extra
from app.services.asset_watch import record_pass
from app.services.fusion import record_clear_passes
from app.services.observations import ingest_observation, publish_event
from app.services.ps26124 import apply_camera_bay
from app.seed import ensure_camera_bays

router = APIRouter(prefix="/demo", tags=["demo"])

# Sample fused pothole site used in the SIH demo narrative
DEMO_LAT = 28.6328
DEMO_LON = 77.2195
USP = "Fleet confirms. One bus cannot."


class DemoStep(BaseModel):
    step: str = "pothole_a"


def _ensure_demo_fleet(db: Session) -> tuple[Bus, Bus, SensorNode | None, SensorNode | None]:
    buses = {b.code: b for b in db.query(Bus).all()}
    if "BUS-042" not in buses:
        bus = Bus(code="BUS-042", registration="DL1PC0042", qr_payload="urbansense://bus/BUS-042")
        db.add(bus)
        db.flush()
        buses["BUS-042"] = bus
    if "BUS-017" not in buses:
        bus = Bus(code="BUS-017", registration="DL1PC0017", qr_payload="urbansense://bus/BUS-017")
        db.add(bus)
        db.flush()
        buses["BUS-017"] = bus
    ensure_camera_bays(db)
    sensors = db.query(SensorNode).all()
    s0 = next((s for s in sensors if s.code == "BUS-042-FRONT"), sensors[0] if sensors else None)
    s1 = next((s for s in sensors if s.code == "BUS-017-FRONT"), sensors[1] if len(sensors) > 1 else s0)
    return buses["BUS-042"], buses["BUS-017"], s0, s1


def _seed_extra(engine: str, *, camera_bay: str | None = None, **more) -> dict:
    extra = {
        "ai_status": "SIMULATED",
        "payload_kind": "SEED",
        "engine_status": engine,
        "derivation": f"Demo seed payload. Engine is {engine}.",
        **more,
    }
    if camera_bay:
        extra["camera_bay"] = camera_bay
    return extra


def _pothole_payload(*, bus: Bus, sensor: SensorNode | None, step: str, lat: float, lon: float, confidence: float) -> ObservationIn:
    now = datetime.now(timezone.utc)
    return ObservationIn(
        event_type=EventType.POTHOLE,
        severity=Severity.HIGH,
        latitude=lat,
        longitude=lon,
        gps_accuracy=4.0,
        timestamp=now,
        source_type=SourceType.PHONE,
        source_id=bus.code,
        sensor_id=sensor.id if sensor else None,
        bus_id=bus.id,
        confidence=confidence,
        simulated=True,
        extra=_seed_extra(
            "REAL",
            camera_bay="FRONT",
            demo_step=step,
            derivation="Demo seed payload. POTHOLE engine is REAL YOLO RDD on stills.",
        ),
    )


def _step_out(ps_line: str, event: UrbanEvent, extra: dict | None = None) -> dict:
    row = {
        "ps_line": ps_line,
        "public_code": event.public_code,
        "event_id": event.id,
        "url": f"/events/{event.id}",
        "event_type": event.event_type.value if event.event_type else None,
        "status": event.status.value if event.status else None,
        "patrol_state": (event.extra or {}).get("patrol_state"),
    }
    if extra:
        row.update(extra)
    return row


@router.post("/start")
async def start_demo(
    body: DemoStep,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)),
):
    """Generate clearly simulated observations for the live demo story."""
    if not get_settings().demo_api_enabled:
        raise HTTPException(status_code=403, detail="Demo API is disabled on this host.")
    b42, b17, s0, s1 = _ensure_demo_fleet(db)
    now = datetime.now(timezone.utc)

    if body.step == "pothole_a":
        payload = _pothole_payload(bus=b42, sensor=s0, step="BUS-042", lat=DEMO_LAT, lon=DEMO_LON, confidence=0.82)
    elif body.step == "pothole_b":
        payload = _pothole_payload(
            bus=b17, sensor=s1, step="BUS-017", lat=DEMO_LAT + 0.0001, lon=DEMO_LON + 0.00008, confidence=0.89
        )
    elif body.step == "reverify":
        payload = ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.LOW,
            latitude=DEMO_LAT,
            longitude=DEMO_LON,
            gps_accuracy=3.0,
            timestamp=now,
            source_type=SourceType.PHONE,
            source_id="RE-SENSE",
            sensor_id=s0.id if s0 else None,
            bus_id=b42.id,
            confidence=0.4,
            simulated=True,
            extra={"demo_step": "re-sense", "note": "Post-repair pass; operator may mark resolved", "payload_kind": "SEED"},
        )
    else:
        payload = ObservationIn(
            event_type=EventType.TRAFFIC_CONGESTION,
            severity=Severity.MEDIUM,
            latitude=DEMO_LAT - 0.002,
            longitude=DEMO_LON + 0.002,
            timestamp=now,
            source_type=SourceType.PHONE,
            source_id=b42.code,
            bus_id=b42.id,
            confidence=0.7,
            simulated=True,
            extra=_seed_extra("RULE_BASED", camera_bay="FRONT", los="E", method="LOS persistence"),
        )
    obs, event, created = ingest_observation(db, payload, actor_id=user.id)
    background.add_task(publish_event, event, created)
    return {
        "observation_id": obs.id,
        "event_id": event.id,
        "public_code": event.public_code,
        "created_event": created,
        "simulated": True,
        "patrol_state": (event.extra or {}).get("patrol_state"),
        "usp": USP,
    }


def _ensure_sign_183(db: Session) -> Asset:
    asset = db.query(Asset).filter(Asset.code == "SIGN-183").first()
    if asset:
        return asset
    asset = Asset(
        code="SIGN-183",
        asset_type=AssetType.TRAFFIC_SIGN,
        name="Stop Sign 183",
        latitude=DEMO_LAT,
        longitude=DEMO_LON,
        qr_payload="urbansense://asset/SIGN-183",
        condition=AssetCondition.GOOD,
    )
    db.add(asset)
    db.flush()
    return asset


@router.post("/jury-run")
async def jury_run(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SUPER_ADMIN)),
):
    """One-click BEL PS 26124 walkthrough. Seed payloads; engines stay honest."""
    if not get_settings().demo_api_enabled:
        raise HTTPException(status_code=403, detail="Demo API is disabled on this host.")
    b42, b17, s0, s1 = _ensure_demo_fleet(db)
    steps: list[dict] = []

    _, first, _ = ingest_observation(
        db,
        _pothole_payload(bus=b42, sensor=s0, step="BUS-042", lat=DEMO_LAT, lon=DEMO_LON, confidence=0.82),
        actor_id=user.id,
    )
    background.add_task(publish_event, first, True)
    steps.append(_step_out("Pothole first sighting — BUS-042 FRONT. One bus opens UNVERIFIED.", first))

    _, confirmed, created_b = ingest_observation(
        db,
        _pothole_payload(
            bus=b17, sensor=s1, step="BUS-017", lat=DEMO_LAT + 0.0001, lon=DEMO_LON + 0.00008, confidence=0.89
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, confirmed, created_b)
    steps.append(
        _step_out(
            "Pothole fleet-confirm — BUS-017 FRONT. Second independent bus is the only auto-confirm.",
            confirmed,
        )
    )

    for src in ("BUS-088", "BUS-091", "BUS-003"):
        record_clear_passes(db, latitude=DEMO_LAT, longitude=DEMO_LON, source_id=src, heading=270)
    db.refresh(confirmed)
    steps.append(
        _step_out(
            "Clear passes on confirmed pothole — three later buses did not re-trigger. Fleet-confirm still stands. Absence does not delete a confirm.",
            confirmed,
            {"clear_pass_count": len((confirmed.extra or {}).get("clear_passes") or [])},
        )
    )

    expire_lat, expire_lon = DEMO_LAT + 0.002, DEMO_LON - 0.002
    _, rumour, rumour_new = ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.MEDIUM,
            latitude=expire_lat,
            longitude=expire_lon,
            gps_accuracy=5.0,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id="BUS-055",
            bus_id=b42.id,
            confidence=0.61,
            simulated=True,
            extra=_seed_extra(
                "REAL",
                camera_bay="FRONT",
                derivation="One-bus rumour. Later clear passes can expire it. Not ground truth.",
            ),
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, rumour, rumour_new)
    for src in ("BUS-088", "BUS-091", "BUS-003"):
        record_clear_passes(db, latitude=expire_lat, longitude=expire_lon, source_id=src, heading=85)
    db.refresh(rumour)
    steps.append(
        _step_out(
            "First sighting expired — three later buses did not re-sense. We will not dispatch a one-bus rumour. RULE_BASED absence.",
            rumour,
        )
    )

    repair_lat, repair_lon = DEMO_LAT - 0.0035, DEMO_LON - 0.0035
    _, patched, patched_new = ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.HIGH,
            latitude=repair_lat,
            longitude=repair_lon,
            gps_accuracy=4.0,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id="BUS-061",
            bus_id=b42.id,
            confidence=0.8,
            simulated=True,
            extra=_seed_extra(
                "REAL",
                camera_bay="FRONT",
                derivation="Separate repair-audit cell. Contractor selfie does not close.",
            ),
        ),
        actor_id=user.id,
    )
    _, patched, _ = ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.POTHOLE,
            severity=Severity.HIGH,
            latitude=repair_lat + 0.00008,
            longitude=repair_lon + 0.00006,
            gps_accuracy=4.0,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id="BUS-062",
            bus_id=b17.id,
            confidence=0.84,
            simulated=True,
            extra=_seed_extra(
                "REAL",
                camera_bay="FRONT",
                derivation="Second bus confirms the cell that will be fleet-audited after repair.",
            ),
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, patched, patched_new)
    wo_code = f"WO-ABS-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    wo = WorkOrder(
        public_code=wo_code,
        event_id=patched.id,
        title="Repair confirmed pothole — fleet will audit",
        description="Contractor selfie does not close. Next independent buses audit.",
        status=WorkOrderStatus.RE_VERIFICATION,
        qr_payload=f"urbansense://work-order/{wo_code}",
        repair_notes="Marked repaired for jury audit.",
    )
    db.add(wo)
    patched.status = EventStatus.RE_VERIFICATION
    extra = dict(patched.extra or {})
    extra["repair_passes"] = []
    extra["repair_opened_at"] = datetime.now(timezone.utc).isoformat()
    write_extra(patched, extra)
    db.flush()
    for src in ("BUS-071", "BUS-072"):
        record_clear_passes(db, latitude=repair_lat, longitude=repair_lon, source_id=src, heading=260)
    db.refresh(patched)
    db.refresh(wo)
    steps.append(
        _step_out(
            "Repair verified by fleet — two later independent buses did not re-sense. Contractor cannot selfie-close. Not certified asphalt.",
            patched,
            {"work_order": wo.public_code, "work_order_status": wo.status.value},
        )
    )
    db.commit()

    sign = _ensure_sign_183(db)
    last_pass: dict = {}
    for i, src in enumerate((b42.code, b17.code, "BUS-088")):
        last_pass = record_pass(
            db,
            sign,
            DEMO_LAT + i * 0.00001,
            DEMO_LON,
            observed=False,
            source_type="PHONE",
            source_id=src,
            actor_id=user.id,
        )
    sign_event = db.get(UrbanEvent, last_pass["event_id"]) if last_pass.get("event_id") else None
    if sign_event is None:
        sign_event = (
            db.query(UrbanEvent)
            .filter(UrbanEvent.event_type == EventType.DAMAGED_SIGN)
            .order_by(UrbanEvent.updated_at.desc())
            .first()
        )
    if sign_event:
        steps.append(
            _step_out(
                "GIS missing-sign — three non-confirming passes on SIGN-183. RULE_BASED, not a neural absence detector.",
                sign_event,
                {"passes": last_pass.get("reason"), "raised": last_pass.get("raised")},
            )
        )

    _, congestion, cong_new = ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.TRAFFIC_CONGESTION,
            severity=Severity.MEDIUM,
            latitude=DEMO_LAT - 0.004,
            longitude=DEMO_LON + 0.004,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id=b42.code,
            bus_id=b42.id,
            confidence=0.74,
            simulated=True,
            extra=_seed_extra(
                "RULE_BASED",
                camera_bay="FRONT",
                los="E",
                method="LOS persistence",
                derivation="Seed congestion. Engine is RULE_BASED LOS, not a traffic-forecast model.",
            ),
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, congestion, cong_new)
    steps.append(_step_out("Congestion / bottleneck — LOS E persistence. RULE_BASED, not a forecast model.", congestion))

    _, rash, rash_new = ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.RASH_DRIVING,
            severity=Severity.HIGH,
            latitude=DEMO_LAT + 0.006,
            longitude=DEMO_LON - 0.003,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id=b42.code,
            bus_id=b42.id,
            confidence=0.88,
            simulated=True,
            plate_text="DL8CAF4321",
            plate_confidence=0.91,
            extra=_seed_extra(
                "RULE_BASED",
                camera_bay="FRONT",
                plate_ai_status="REAL",
                derivation="Seed rash + ANPR fields. Plate masked until ADMIN/INSPECTOR. ASSISTS AUTHORITIES — DOES NOT ACCUSE.",
                assist_line="ASSISTS AUTHORITIES — DOES NOT ACCUSE",
            ),
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, rash, rash_new)
    steps.append(_step_out("Rash driving + plate — ANPR fields present, DPDP masked. Assists authorities, does not accuse.", rash))

    cabin_type, cabin_note = apply_camera_bay(EventType.POTHOLE, "CABIN")
    _, cabin, cabin_new = ingest_observation(
        db,
        ObservationIn(
            event_type=cabin_type,
            severity=Severity.LOW,
            latitude=DEMO_LAT + 0.008,
            longitude=DEMO_LON + 0.006,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id=f"{b42.code}-CABIN",
            bus_id=b42.id,
            confidence=0.4,
            simulated=True,
            extra=_seed_extra(
                "REAL",
                camera_bay="CABIN",
                camera_bay_note=cabin_note,
                derivation="Cabin still cannot invent a road defect. PS 26124 cabin vs road split.",
            ),
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, cabin, cabin_new)
    steps.append(
        _step_out(
            "Cabin camera — CABIN bay must not become POTHOLE. Cabin only.",
            cabin,
            {"camera_bay": "CABIN", "would_have_been": "POTHOLE"},
        )
    )

    _, water, water_new = ingest_observation(
        db,
        ObservationIn(
            event_type=EventType.WATERLOGGING,
            severity=Severity.MEDIUM,
            latitude=DEMO_LAT - 0.007,
            longitude=DEMO_LON - 0.005,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.PHONE,
            source_id=b17.code,
            bus_id=b17.id,
            confidence=0.55,
            simulated=True,
            extra=_seed_extra(
                "SIMULATED",
                camera_bay="FRONT",
                derivation="No dedicated waterlogging net. Explicit SIMULATED seed — not a flood detector.",
            ),
        ),
        actor_id=user.id,
    )
    background.add_task(publish_event, water, water_new)
    steps.append(_step_out("Waterlogging — explicit SIMULATED. No neural flood model.", water))

    return {"usp": USP, "steps": steps}
