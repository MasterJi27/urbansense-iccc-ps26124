"""Ward → bus → windshield phone. Admin allocates; the phone is only a still service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.fleet import Bus, ProcessingMode, SensorNode, Ward


def upsert_ward(db: Session, number: int, name: str | None = None, zone: str | None = None) -> Ward:
    row = db.query(Ward).filter(Ward.number == int(number)).first()
    if row is None:
        row = Ward(number=int(number), name=name or f"Ward {number}", zone=zone or "")
        db.add(row)
        db.flush()
        return row
    if name:
        row.name = name
    if zone is not None:
        row.zone = zone
    return row


def allocate(db: Session, *, ward_number: int, bus_code: str, phone_code: str, zone: str = "") -> dict:
    bus_code = bus_code.strip().upper()
    phone_code = phone_code.strip().upper()
    bus = db.query(Bus).filter(Bus.code == bus_code).first()
    if bus is None:
        bus = Bus(code=bus_code, registration="", qr_payload=f"urbansense://bus/{bus_code}")
        db.add(bus)
        db.flush()
    ward = upsert_ward(db, ward_number, zone=zone)
    bus.ward_id = ward.id
    node = db.query(SensorNode).filter(SensorNode.code == phone_code).first()
    if node is None:
        node = SensorNode(code=phone_code, device_label="WINDSHIELD_PHONE", source_type="PHONE")
        db.add(node)
        db.flush()
    node.bus_id = bus.id
    node.device_label = "WINDSHIELD_PHONE"
    node.source_type = "PHONE"
    node.processing_mode = ProcessingMode.CAPTURE_AND_SENSOR
    node.camera_status = "ONLINE"
    db.commit()
    db.refresh(node)
    return assignment_row(db, bus, node, ward)


def assignment_row(db: Session, bus: Bus, node: SensorNode | None, ward: Ward | None) -> dict:
    online = False
    if node and node.last_heartbeat_at:
        age = (datetime.now(timezone.utc) - node.last_heartbeat_at.replace(tzinfo=timezone.utc)).total_seconds()
        online = age < 45
    return {
        "ward_number": ward.number if ward else None,
        "ward_name": ward.name if ward else None,
        "zone": ward.zone if ward else None,
        "bus_code": bus.code,
        "bus_id": bus.id,
        "phone_code": node.code if node else None,
        "phone_id": node.id if node else None,
        "camera_status": node.camera_status if node else "UNKNOWN",
        "gps_status": node.gps_status if node else "UNKNOWN",
        "imu_status": node.imu_status if node else "UNKNOWN",
        "patrol_mode": node.patrol_mode if node else "AUTO",
        "online": online,
        "last_heartbeat_at": node.last_heartbeat_at if node else None,
        "last_evidence_url": node.last_evidence_url if node else None,
        "last_detect_at": node.last_detect_at if node else None,
        "latitude": node.latitude if node else None,
        "longitude": node.longitude if node else None,
    }


def matrix(db: Session) -> list[dict]:
    rows = []
    for bus in db.query(Bus).order_by(Bus.code).all():
        ward = db.get(Ward, bus.ward_id) if bus.ward_id else None
        phone = next(
            (
                n
                for n in db.query(SensorNode).filter(SensorNode.bus_id == bus.id, SensorNode.source_type == "PHONE").all()
                if (n.device_label or "").upper() in {"WINDSHIELD_PHONE", "PHONE"}
            ),
            None,
        )
        if phone is None:
            phone = db.query(SensorNode).filter(SensorNode.bus_id == bus.id, SensorNode.source_type == "PHONE").first()
        rows.append(assignment_row(db, bus, phone, ward))
    return rows


def assignment_for_bus(db: Session, bus_code: str) -> dict | None:
    bus = db.query(Bus).filter(Bus.code == bus_code.strip().upper()).first()
    if bus is None:
        return None
    ward = db.get(Ward, bus.ward_id) if bus.ward_id else None
    phone = next(
        (
            n
            for n in db.query(SensorNode).filter(SensorNode.bus_id == bus.id, SensorNode.source_type == "PHONE").all()
            if (n.device_label or "").upper() in {"WINDSHIELD_PHONE", "PHONE"}
        ),
        None,
    )
    if phone is None:
        phone = db.query(SensorNode).filter(SensorNode.bus_id == bus.id, SensorNode.source_type == "PHONE").first()
    return assignment_row(db, bus, phone, ward)


def touch_phone_feed(
    db: Session,
    *,
    source_id: str | None,
    bus_fk: str | None,
    bus_code: str | None,
    evidence_url: str | None,
    patrol_mode: str | None = None,
) -> None:
    if not evidence_url and not patrol_mode:
        return
    node = None
    if source_id:
        node = db.query(SensorNode).filter(SensorNode.code == source_id).first()
    if node is None and bus_fk:
        node = (
            db.query(SensorNode)
            .filter(SensorNode.bus_id == bus_fk, SensorNode.source_type == "PHONE")
            .first()
        )
    if node is None and bus_code:
        bus = db.query(Bus).filter(Bus.code == str(bus_code).upper()).first()
        if bus:
            node = (
                db.query(SensorNode)
                .filter(SensorNode.bus_id == bus.id, SensorNode.source_type == "PHONE")
                .first()
            )
    if node is None:
        return
    if evidence_url:
        node.last_evidence_url = evidence_url
        node.last_detect_at = datetime.now(timezone.utc)
        node.camera_status = "ONLINE"
    if patrol_mode in {"AUTO", "MANUAL"}:
        node.patrol_mode = patrol_mode
