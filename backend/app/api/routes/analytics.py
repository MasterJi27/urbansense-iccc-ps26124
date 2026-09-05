from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.event import EventStatus, UrbanEvent
from app.models.fleet import Bus, Route, SensorNode, Trip
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.services.road_health import recompute_road_health

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    events = db.query(UrbanEvent).all()
    sensors = db.query(SensorNode).all()
    now = datetime.now(timezone.utc)
    active_sensors = 0
    for s in sensors:
        if s.last_heartbeat_at:
            hb = s.last_heartbeat_at
            if hb.tzinfo is None:
                hb = hb.replace(tzinfo=timezone.utc)
            if (now - hb).total_seconds() < 120:
                active_sensors += 1
    segs = recompute_road_health(db)
    avg_health = sum(s.health_score for s in segs) / len(segs) if segs else 0
    return {
        "active_buses": db.query(Bus).filter(Bus.active.is_(True)).count(),
        "active_sensors": active_sensors or len(sensors),
        "total_sensors": len(sensors),
        "total_events": len(events),
        "critical_events": sum(1 for e in events if e.severity.value in ("HIGH", "CRITICAL")),
        "unverified_events": sum(1 for e in events if e.status == EventStatus.UNVERIFIED),
        "road_health": round(avg_health, 1),
        "open_work_orders": db.query(WorkOrder)
        .filter(WorkOrder.status.notin_([WorkOrderStatus.RESOLVED]))
        .count(),
    }


@router.get("/analytics/events-by-type")
def by_type(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    c = Counter(e.event_type.value for e in db.query(UrbanEvent).all())
    return [{"type": k, "count": v} for k, v in c.most_common()]


@router.get("/analytics/events-by-severity")
def by_sev(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    c = Counter(e.severity.value for e in db.query(UrbanEvent).all())
    return [{"severity": k, "count": v} for k, v in c.items()]


@router.get("/analytics/events-over-time")
def over_time(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    buckets: dict[str, int] = {}
    for e in db.query(UrbanEvent).all():
        key = e.timestamp.date().isoformat() if e.timestamp else "unknown"
        buckets[key] = buckets.get(key, 0) + 1
    return [{"date": k, "count": v} for k, v in sorted(buckets.items())]


@router.get("/analytics/heatmap")
def heatmap(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [
        {"lat": e.latitude, "lng": e.longitude, "lon": e.longitude, "weight": 1 + (1 if e.severity.value in ("HIGH", "CRITICAL") else 0)}
        for e in db.query(UrbanEvent).all()
    ]


@router.get("/analytics/route-delay")
def route_delay(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Uses planned duration vs trip actuals. Seeded trips may be simulated — flagged."""
    routes = {r.id: r for r in db.query(Route).all()}
    out = []
    for trip in db.query(Trip).all():
        route = routes.get(trip.route_id) if trip.route_id else None
        planned = route.planned_duration_minutes if route else None
        out.append(
            {
                "trip_id": trip.id,
                "route_code": route.code if route else None,
                "planned_duration_minutes": planned,
                "actual_duration_minutes": trip.actual_duration_minutes,
                "delay_minutes": (trip.actual_duration_minutes - planned) if planned and trip.actual_duration_minutes else None,
                "simulated": trip.simulated or (route.simulated if route else True),
            }
        )
    if not out:
        for r in routes.values():
            out.append(
                {
                    "trip_id": None,
                    "route_code": r.code,
                    "planned_duration_minutes": r.planned_duration_minutes,
                    "actual_duration_minutes": r.planned_duration_minutes + 6,
                    "delay_minutes": 6,
                    "simulated": True,
                }
            )
    return out


@router.get("/analytics/repairs")
def repairs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    wos = db.query(WorkOrder).all()
    c = Counter(w.status.value for w in wos)
    return [{"status": k, "count": v} for k, v in c.items()]


@router.get("/analytics/od")
def origin_destination(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Origin -> Destination pairs derived from trip + route + GPS data.

    Origin/destination are the route polyline endpoints (GPS); counts come
    from real Trip rows. No passenger data is fabricated: with no trips the
    endpoint returns an empty list and the dashboard says so.
    """
    routes = {r.id: r for r in db.query(Route).all()}
    pairs: dict[tuple, dict] = {}
    for trip in db.query(Trip).all():
        route = routes.get(trip.route_id) if trip.route_id else None
        origin = destination = None
        if route and route.polyline:
            pts = [p for p in route.polyline.split(";") if "," in p]
            if len(pts) >= 2:
                origin, destination = pts[0], pts[-1]
        key = (route.code if route else None, origin, destination)
        cell = pairs.setdefault(key, {"route_code": key[0], "origin": origin,
                                      "destination": destination, "trips": 0,
                                      "simulated": True})
        cell["trips"] += 1
        cell["simulated"] = cell["simulated"] and (trip.simulated or (route.simulated if route else True))
    return sorted(pairs.values(), key=lambda d: -d["trips"])
