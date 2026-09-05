from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.fleet import Bus
from app.models.work_order import WorkOrder


def lookup(db: Session, payload: str) -> dict:
    raw = payload.strip()
    if raw.startswith("urbansense://"):
        parts = raw.replace("urbansense://", "").split("/")
        kind = parts[0] if parts else ""
        ident = parts[1] if len(parts) > 1 else ""
    elif ":" in raw:
        kind, ident = raw.split(":", 1)
    else:
        kind, ident = "unknown", raw

    kind = kind.replace("_", "-").lower()
    if kind in ("bus",):
        bus = db.query(Bus).filter((Bus.code == ident) | (Bus.qr_payload == raw) | (Bus.id == ident)).first()
        if not bus:
            return {"kind": "bus", "found": False}
        return {
            "kind": "bus",
            "found": True,
            "id": bus.id,
            "code": bus.code,
            "route_id": bus.route_id,
            "qr_payload": bus.qr_payload,
        }
    if kind in ("asset",):
        asset = db.query(Asset).filter((Asset.code == ident) | (Asset.qr_payload == raw) | (Asset.id == ident)).first()
        if not asset:
            return {"kind": "asset", "found": False}
        return {
            "kind": "asset",
            "found": True,
            "id": asset.id,
            "code": asset.code,
            "asset_type": asset.asset_type.value,
            "condition": asset.condition.value,
            "latitude": asset.latitude,
            "longitude": asset.longitude,
            "qr_payload": asset.qr_payload,
        }
    if kind in ("work-order", "workorder", "wo"):
        wo = (
            db.query(WorkOrder)
            .filter((WorkOrder.public_code == ident) | (WorkOrder.qr_payload == raw) | (WorkOrder.id == ident))
            .first()
        )
        if not wo:
            return {"kind": "work_order", "found": False}
        return {
            "kind": "work_order",
            "found": True,
            "id": wo.id,
            "public_code": wo.public_code,
            "status": wo.status.value,
            "title": wo.title,
            "event_id": wo.event_id,
        }
    if kind in ("event",):
        return {"kind": "event", "found": True, "id": ident, "code": ident}

    bus = db.query(Bus).filter((Bus.qr_payload == raw) | (Bus.code == raw)).first()
    if bus:
        return lookup(db, bus.qr_payload)
    asset = db.query(Asset).filter((Asset.qr_payload == raw) | (Asset.code == raw)).first()
    if asset:
        return lookup(db, asset.qr_payload)
    wo = db.query(WorkOrder).filter((WorkOrder.qr_payload == raw) | (WorkOrder.public_code == raw)).first()
    if wo:
        return lookup(db, wo.qr_payload)
    return {"kind": "unknown", "found": False, "raw": raw}
