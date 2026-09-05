from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_roles
from app.models.asset import Asset, AssetCondition, AssetPass, AssetType, Inspection, RoadSegment
from app.models.event import UrbanEvent
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder
from app.schemas.common import AssetIn, AssetPassIn, InspectIn
from app.services.asset_watch import PASS_RADIUS_M, PASSES_REQUIRED, record_pass
from app.services.qr import lookup
from app.services.road_health import recompute_road_health

router = APIRouter(tags=["assets"])


@router.get("/assets")
def list_assets(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_asset_out(a) for a in db.query(Asset).all()]


@router.post("/assets")
def create_asset(body: AssetIn, db: Session = Depends(get_db), _: User = Depends(require_roles(UserRole.ADMIN))):
    asset = Asset(
        code=body.code,
        asset_type=AssetType(body.asset_type),
        name=body.name,
        latitude=body.latitude,
        longitude=body.longitude,
        qr_payload=f"urbansense://asset/{body.code}",
        condition=AssetCondition(body.condition),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _asset_out(asset)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    asset = db.get(Asset, asset_id) or db.query(Asset).filter(Asset.code == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    events = db.query(UrbanEvent).filter(UrbanEvent.asset_id == asset.id).all()
    nearby = (
        db.query(UrbanEvent)
        .filter(
            UrbanEvent.latitude.between(asset.latitude - 0.002, asset.latitude + 0.002),
            UrbanEvent.longitude.between(asset.longitude - 0.002, asset.longitude + 0.002),
        )
        .all()
    )
    inspections = db.query(Inspection).filter(Inspection.asset_id == asset.id).order_by(Inspection.created_at.desc()).all()
    wos = db.query(WorkOrder).filter(WorkOrder.asset_id == asset.id).all()
    return {
        **_asset_out(asset),
        "events": [{"id": e.id, "public_code": e.public_code, "status": e.status.value, "event_type": e.event_type.value} for e in (events or nearby[:8])],
        "inspections": [
            {"id": i.id, "notes": i.notes, "condition": i.condition.value, "checklist": i.checklist, "created_at": i.created_at} for i in inspections
        ],
        "work_orders": [{"id": w.id, "public_code": w.public_code, "status": w.status.value, "repair_evidence_url": w.repair_evidence_url, "repair_notes": w.repair_notes, "title": w.title, "updated_at": w.updated_at} for w in wos],
        "timeline": _timeline(nearby, wos, inspections),
    }


@router.post("/assets/{asset_id}/inspect")
def inspect_asset(asset_id: str, body: InspectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    asset = db.get(Asset, asset_id) or db.query(Asset).filter(Asset.code == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    checklist: dict = {}
    if body.checklist:
        checklist = dict(body.checklist)
    for k in ("joint_gap", "bearing", "crack", "waterlogging", "overall"):
        v = getattr(body, k)
        if v is not None:
            checklist[k] = v
    if not checklist:
        raise HTTPException(400, "checklist required: provide joint_gap, bearing, crack, waterlogging, overall")
    cond = AssetCondition.UNKNOWN
    if body.condition:
        try:
            cond = AssetCondition(str(body.condition).upper())
        except Exception:
            cond = AssetCondition.UNKNOWN
    elif checklist.get("overall"):
        ov = str(checklist["overall"]).upper()
        if ov in AssetCondition.__members__:
            cond = AssetCondition(ov)
    ins = Inspection(asset_id=asset.id, inspector_id=user.id, notes=body.notes or "", condition=cond, checklist=checklist)
    db.add(ins)
    if cond != AssetCondition.UNKNOWN:
        asset.condition = cond
    db.commit()
    db.refresh(ins)
    return {"id": ins.id, "asset_id": asset.id, "checklist": ins.checklist, "notes": ins.notes, "condition": ins.condition.value, "created_at": ins.created_at}


@router.post("/assets/{asset_id}/qr")
def asset_qr(asset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    return {"qr_payload": asset.qr_payload}


@router.post("/assets/{asset_id}/passes")
def asset_pass(
    asset_id: str,
    body: AssetPassIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Record one bus-camera pass by an expected asset.

    Repeated non-confirming passes raise a GIS-derived possible-missing
    event (RULE_BASED). See services.asset_watch.
    """
    asset = db.get(Asset, asset_id) or db.query(Asset).filter(Asset.code == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    return {
        "asset_code": asset.code,
        "thresholds": {"passes_required": PASSES_REQUIRED, "radius_m": PASS_RADIUS_M},
        **record_pass(
            db,
            asset,
            body.latitude,
            body.longitude,
            body.observed,
            body.source_type,
            body.source_id,
            actor_id=user.id,
        ),
    }


@router.get("/assets/{asset_id}/passes")
def asset_passes(asset_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    asset = db.get(Asset, asset_id) or db.query(Asset).filter(Asset.code == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    rows = db.query(AssetPass).filter(AssetPass.asset_id == asset.id).order_by(AssetPass.created_at.desc()).limit(50).all()
    return [
        {"id": p.id, "latitude": p.latitude, "longitude": p.longitude, "observed": p.observed,
         "source_id": p.source_id, "created_at": p.created_at}
        for p in rows
    ]


@router.get("/qr/lookup")
def qr_lookup(payload: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return lookup(db, payload)


@router.get("/road-health")
def road_health(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    segs = recompute_road_health(db)
    db.commit()
    return sorted(
        [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "latitude": s.latitude,
                "longitude": s.longitude,
                "health_score": s.health_score,
                "active_defects": s.active_defects,
                "recurrence_count": s.recurrence_count,
                "traffic_exposure": s.traffic_exposure,
                "pedestrian_exposure": s.pedestrian_exposure,
            }
            for s in segs
        ],
        key=lambda x: x["health_score"],
    )


def _asset_out(a: Asset) -> dict:
    return {
        "id": a.id,
        "code": a.code,
        "asset_type": a.asset_type.value,
        "name": a.name,
        "latitude": a.latitude,
        "longitude": a.longitude,
        "qr_payload": a.qr_payload,
        "condition": a.condition.value,
        "health_score": a.health_score,
        "notes": a.notes,
    }


def _timeline(events, wos, inspections) -> list[dict]:
    items = []
    for e in events:
        items.append({"at": e.created_at, "label": "Detected", "detail": e.public_code})
        if e.status.value in ("CONFIRMED", "ASSIGNED", "IN_PROGRESS", "REPAIRED", "RESOLVED"):
            items.append({"at": e.updated_at, "label": e.status.value.title(), "detail": e.public_code})
    for w in wos:
        items.append({"at": w.created_at, "label": "Work order", "detail": w.public_code})
    for i in inspections:
        chk = i.checklist or {}
        detail = f"{i.condition.value} overall:{chk.get('overall','')} {i.notes[:60]}".strip() if chk else (i.notes[:80] or i.condition.value)
        items.append({"at": i.created_at, "label": "Inspection", "detail": detail})
    items.sort(key=lambda x: x["at"] or "")
    return items
