from sqlalchemy.orm import Session

from app.config import get_settings
from app.geo import haversine_m
from app.models.asset import RoadSegment
from app.models.event import EventStatus, Severity, UrbanEvent


ACTIVE = {
    EventStatus.NEW,
    EventStatus.UNVERIFIED,
    EventStatus.CONFIRMED,
    EventStatus.ASSIGNED,
    EventStatus.IN_PROGRESS,
    EventStatus.REPAIRED,
    EventStatus.RE_VERIFICATION,
    EventStatus.REOPENED,
}


def recompute_road_health(db: Session) -> list[RoadSegment]:
    settings = get_settings()
    segments = db.query(RoadSegment).all()
    events = db.query(UrbanEvent).all()
    for seg in segments:
        nearby = [
            e
            for e in events
            if haversine_m(seg.latitude, seg.longitude, e.latitude, e.longitude) <= 180
        ]
        active = [e for e in nearby if e.status in ACTIVE]
        resolved_like = [e for e in nearby if e.status in (EventStatus.RESOLVED, EventStatus.REOPENED)]
        high = sum(1 for e in active if e.severity in (Severity.HIGH, Severity.CRITICAL))
        recurrence = len(resolved_like)
        score = 100.0
        score -= settings.health_defect_penalty * len(active)
        score -= settings.health_severity_high * high
        score -= settings.health_recurrence_penalty * recurrence
        score -= settings.health_traffic_weight * seg.traffic_exposure
        score -= settings.health_pedestrian_weight * seg.pedestrian_exposure
        seg.health_score = max(0.0, min(100.0, score))
        seg.active_defects = len(active)
        seg.recurrence_count = recurrence
    db.flush()
    return segments
