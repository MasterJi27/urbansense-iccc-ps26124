"""Officer event-ticket purge. Does not touch login, buses, booth PIN, or accounts."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.event import EventObservation, Evidence, Observation, UrbanEvent
from app.models.work_order import WorkOrder
from app.realtime.hub import hub
from app.services.audit import audit
from app.services.road_health import recompute_road_health

CLEAR_NOTE = (
    "Tickets wiped. Buses, officer accounts, and booth PIN stay. "
    "SEED rows return only if this process reseeds an empty database."
)


def purge_event_tickets(db: Session, event_ids: list[str] | None = None) -> list[str]:
    if event_ids is None:
        ids = [row.id for row in db.query(UrbanEvent).all()]
        db.query(WorkOrder).update({WorkOrder.event_id: None}, synchronize_session=False)
        db.query(EventObservation).delete(synchronize_session=False)
        db.query(Evidence).delete(synchronize_session=False)
        db.query(Observation).delete(synchronize_session=False)
        db.query(UrbanEvent).delete(synchronize_session=False)
        return ids

    wanted = [eid for eid in event_ids if eid]
    if not wanted:
        return []
    events = db.query(UrbanEvent).filter(UrbanEvent.id.in_(wanted)).all()
    ids = [row.id for row in events]
    if not ids:
        return []

    links = db.query(EventObservation).filter(EventObservation.event_id.in_(ids)).all()
    obs_ids = [lnk.observation_id for lnk in links]
    db.query(EventObservation).filter(EventObservation.event_id.in_(ids)).delete(synchronize_session=False)
    db.query(Evidence).filter(Evidence.event_id.in_(ids)).delete(synchronize_session=False)
    if obs_ids:
        db.query(Evidence).filter(Evidence.observation_id.in_(obs_ids)).delete(synchronize_session=False)
        leftover = {
            row.observation_id
            for row in db.query(EventObservation).filter(EventObservation.observation_id.in_(obs_ids)).all()
        }
        orphan = [oid for oid in obs_ids if oid not in leftover]
        if orphan:
            db.query(Observation).filter(Observation.id.in_(orphan)).delete(synchronize_session=False)
    db.query(WorkOrder).filter(WorkOrder.event_id.in_(ids)).update(
        {WorkOrder.event_id: None},
        synchronize_session=False,
    )
    db.query(UrbanEvent).filter(UrbanEvent.id.in_(ids)).delete(synchronize_session=False)
    return ids


def commit_purge(db: Session, ids: list[str], actor_id: str | None, detail: str) -> list[str]:
    audit(db, "event.purge", "event", ids[0] if ids else "none", actor_id, detail)
    recompute_road_health(db)
    db.commit()
    return ids


async def publish_deleted(event_ids: list[str]) -> None:
    for eid in event_ids:
        await hub.broadcast({"type": "event.deleted", "event_id": eid, "event": {"id": eid}})


async def publish_cleared() -> None:
    await hub.broadcast({"type": "events.cleared"})
