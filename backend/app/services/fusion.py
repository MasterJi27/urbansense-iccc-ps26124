"""
Deterministic spatial-temporal observation fusion.

Established technique: spatial-temporal clustering of crowdsourced reports
(common in mobile crowdsensing literature).

Project-specific: source diversity + human verification bonuses; no averaging of
confidence; configurable thresholds; replaceable FusionEngine interface.

This is NOT a statistical claim of ground-truth certainty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.geo import bounding_box, haversine_m, validate_coords
from app.models.event import EventObservation, EventStatus, EventType, Observation, Severity, SourceType, UrbanEvent
from app.models.user import uuid_str
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.persist import write_extra

logger = logging.getLogger(__name__)


COMPATIBLE: dict[EventType, set[EventType]] = {
    EventType.POTHOLE: {EventType.POTHOLE, EventType.ROAD_DAMAGE},
    EventType.ROAD_DAMAGE: {EventType.ROAD_DAMAGE, EventType.POTHOLE},
    EventType.WATERLOGGING: {EventType.WATERLOGGING},
    EventType.MISSING_DIVIDER: {EventType.MISSING_DIVIDER},
    EventType.MISSING_ZEBRA: {EventType.MISSING_ZEBRA},
    EventType.DAMAGED_SIGN: {EventType.DAMAGED_SIGN},
    EventType.ROAD_OBSTRUCTION: {EventType.ROAD_OBSTRUCTION},
    EventType.TRAFFIC_CONGESTION: {EventType.TRAFFIC_CONGESTION},
    EventType.PEDESTRIAN_RISK: {EventType.PEDESTRIAN_RISK, EventType.SCHOOL_CROSSING},
    EventType.SCHOOL_CROSSING: {EventType.SCHOOL_CROSSING, EventType.PEDESTRIAN_RISK},
    EventType.HIT_AND_RUN: {EventType.HIT_AND_RUN, EventType.RASH_DRIVING},
    EventType.RASH_DRIVING: {EventType.RASH_DRIVING, EventType.HIT_AND_RUN},
    EventType.VEHICLE: {EventType.VEHICLE},
    EventType.PEDESTRIAN: {EventType.PEDESTRIAN},
    EventType.BRIDGE_VIBRATION: {EventType.BRIDGE_VIBRATION, EventType.BRIDGE_ANOMALY, EventType.FLYOVER_JOINT},
    EventType.FLYOVER_JOINT: {EventType.FLYOVER_JOINT, EventType.BRIDGE_VIBRATION, EventType.BRIDGE_ANOMALY},
    EventType.BRIDGE_ANOMALY: {EventType.BRIDGE_ANOMALY, EventType.BRIDGE_VIBRATION, EventType.FLYOVER_JOINT},
    EventType.OTHER: {EventType.OTHER},
}


@dataclass
class FusionResult:
    event: UrbanEvent
    created: bool
    distance_m: float | None
    reason: str


class FusionEngine:
    """Replaceable interface. MVP: deterministic clustering."""

    def fuse(self, db: Session, observation: Observation) -> FusionResult:
        raise NotImplementedError


class SpatialTemporalFusionEngine(FusionEngine):
    def fuse(self, db: Session, observation: Observation) -> FusionResult:
        settings = get_settings()
        validate_coords(observation.latitude, observation.longitude)
        ts = observation.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        candidates = _nearby_events(db, observation.latitude, observation.longitude)

        best: UrbanEvent | None = None
        best_d: float | None = None
        for ev in candidates:
            types = COMPATIBLE.get(observation.event_type, {observation.event_type})
            if settings.fusion_compatible_only and ev.event_type not in types:
                continue
            ev_ts = ev.timestamp
            if ev_ts.tzinfo is None:
                ev_ts = ev_ts.replace(tzinfo=timezone.utc)
            dt = abs((ts - ev_ts).total_seconds())
            if dt > settings.fusion_max_time_seconds:
                continue
            dist = haversine_m(observation.latitude, observation.longitude, ev.latitude, ev.longitude)
            if dist > settings.fusion_max_distance_meters:
                continue
            if best is None or dist < (best_d or 1e12):
                best, best_d = ev, dist

        if best is None:
            event = _new_event_from_obs(observation)
            db.add(event)
            db.flush()
            db.add(EventObservation(event_id=event.id, observation_id=observation.id, distance_m=0))
            event.fusion_reason = (
                "New event: no compatible observation within "
                f"{settings.fusion_max_distance_meters}m / {settings.fusion_max_time_seconds}s. "
                "First sighting — waiting for a second independent bus."
            )
            _stamp_patrol(event, [observation])
            logger.info(
                "fusion new_event code=%s obs=%s type=%s reason=%s",
                event.public_code,
                observation.id,
                observation.event_type.value,
                event.fusion_reason,
            )
            return FusionResult(event=event, created=True, distance_m=None, reason=event.fusion_reason)

        _attach(db, best, observation, best_d or 0)
        logger.info(
            "fusion attach obs=%s event=%s distance=%.1f reason=%s",
            observation.id,
            best.public_code,
            best_d or 0,
            best.fusion_reason,
        )
        return FusionResult(event=best, created=False, distance_m=best_d, reason=best.fusion_reason)


def _new_event_from_obs(obs: Observation) -> UrbanEvent:
    seq = obs.id.replace("-", "")[:6].upper()
    return UrbanEvent(
        public_code=f"EVENT-{seq}",
        event_type=obs.event_type,
        severity=obs.severity,
        status=EventStatus.UNVERIFIED,
        latitude=obs.latitude,
        longitude=obs.longitude,
        gps_accuracy=obs.gps_accuracy,
        timestamp=obs.timestamp,
        source_id=obs.source_id,
        sensor_id=obs.sensor_id,
        bus_id=obs.bus_id,
        route_id=obs.route_id,
        confidence=obs.confidence,
        evidence_url=obs.evidence_url,
        thumbnail_url=obs.thumbnail_url,
        extra=obs.extra,
        fusion_group_id=uuid_str(),
        verification_count=1 if obs.source_type == SourceType.INSPECTOR else 0,
        source_count=1,
        observation_count=1,
        simulated=obs.simulated,
    )


def _attach(db: Session, event: UrbanEvent, obs: Observation, distance_m: float) -> None:
    db.add(EventObservation(event_id=event.id, observation_id=obs.id, distance_m=distance_m))
    db.flush()
    links = db.scalars(select(EventObservation).where(EventObservation.event_id == event.id)).all()
    obs_ids = [lnk.observation_id for lnk in links]
    observations = db.scalars(select(Observation).where(Observation.id.in_(obs_ids))).all()
    observations = list(observations) + [obs]
    # de-dupe by id
    by_id = {o.id: o for o in observations}
    observations = list(by_id.values())

    sources = {o.source_id for o in observations}
    source_types = {o.source_type for o in observations}
    confidences = [o.confidence for o in observations]
    human = any(o.source_type == SourceType.INSPECTOR for o in observations)

    # Transparent weighting — not a statistical average.
    base = max(confidences) if confidences else 0.5
    diversity_bonus = min(0.15, 0.05 * max(0, len(sources) - 1))
    type_bonus = min(0.08, 0.04 * max(0, len(source_types) - 1))
    human_bonus = 0.12 if human else 0.0
    fused = min(0.99, base + diversity_bonus + type_bonus + human_bonus)

    n = len(observations)
    event.latitude = sum(o.latitude for o in observations) / n
    event.longitude = sum(o.longitude for o in observations) / n
    event.confidence = fused
    event.source_count = len(sources)
    event.observation_count = n
    event.verification_count = sum(1 for o in observations if o.source_type == SourceType.INSPECTOR)
    if obs.severity == Severity.CRITICAL or event.severity == Severity.CRITICAL:
        event.severity = Severity.CRITICAL
    elif obs.severity == Severity.HIGH and event.severity in (Severity.LOW, Severity.MEDIUM):
        event.severity = Severity.HIGH
    if not event.evidence_url and obs.evidence_url:
        event.evidence_url = obs.evidence_url
    if human and event.status == EventStatus.UNVERIFIED:
        event.status = EventStatus.CONFIRMED
    event.simulated = event.simulated or obs.simulated
    _maybe_reopen_after_resense(db, event, obs)
    _stamp_patrol(event, observations, incoming=obs)
    extra = dict(event.extra or {})
    kinds = {((o.extra or {}).get("payload_kind")) for o in observations}
    if "SEED" in kinds or event.simulated:
        extra.setdefault("payload_kind", "SEED")
        extra.setdefault("ai_status", "SIMULATED")
    engines = [((o.extra or {}).get("engine_status")) for o in observations if (o.extra or {}).get("engine_status")]
    if engines:
        extra["engine_status"] = engines[0]
    write_extra(event, extra)
    patrol = (event.extra or {}).get("patrol_state")
    event.fusion_reason = (
        f"spatial proximity (~{distance_m:.1f}m); temporal window; compatible type {obs.event_type.value}; "
        f"source diversity ({len(sources)} sources, {len(source_types)} source types"
        f"{'; human verification' if human else ''}"
        f"{'; second bus fleet-confirm' if patrol == 'FLEET_CONFIRMED' else '; still first sighting'}). "
        f"Evidence score = max(confidence) {base:.2f} + diversity {diversity_bonus:.2f} "
        f"+ type {type_bonus:.2f} + human {human_bonus:.2f} = {fused:.2f}. Not statistical certainty."
    )


_FLEET_SOURCES = {SourceType.PHONE, SourceType.BUS_CCTV, SourceType.IOT, SourceType.ROAD_CCTV}
_CLEAR_PASS_TYPES = {EventType.POTHOLE, EventType.ROAD_DAMAGE, EventType.ROAD_OBSTRUCTION}
_REPAIR_TRIGGER_TYPES = {EventType.POTHOLE, EventType.ROAD_DAMAGE}


def _aware(ts: datetime | None) -> datetime:
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _obs_sort_key(obs: Observation) -> tuple:
    return (_aware(obs.timestamp), _aware(getattr(obs, "created_at", None)), obs.id)


def _fleet_ids(observations: list[Observation]) -> list[str]:
    ordered: list[str] = []
    for obs in sorted(observations, key=_obs_sort_key):
        if obs.source_type in _FLEET_SOURCES and obs.source_id and obs.source_id not in ordered:
            ordered.append(obs.source_id)
    return ordered


def build_confirmation_ledger(event: UrbanEvent, observations: list[Observation]) -> dict:
    """Independent-Bus Confirmation Ledger — jury-facing, ordered unique buses."""
    rows = sorted(observations, key=_obs_sort_key)
    unique: list[dict] = []
    seen: set[str] = set()
    same_bus_ignored = 0
    bays: list[str] = []
    for obs in rows:
        bay = ((obs.extra or {}).get("camera_bay") or "").upper() or None
        if bay and bay not in bays:
            bays.append(bay)
        fleet = obs.source_type in _FLEET_SOURCES and bool(obs.source_id)
        if not fleet:
            continue
        if obs.source_id in seen:
            same_bus_ignored += 1
            continue
        seen.add(obs.source_id)
        unique.append(
            {
                "source_id": obs.source_id,
                "source_type": obs.source_type.value if obs.source_type else None,
                "timestamp": obs.timestamp.isoformat() if obs.timestamp else None,
                "camera_bay": bay,
            }
        )
    extra = event.extra or {}
    first = unique[0] if unique else None
    confirm = unique[1] if len(unique) > 1 else None
    clear_passes = list(extra.get("clear_passes") or [])
    first_heading = next((o.heading for o in rows if o.source_id == (first or {}).get("source_id") and o.heading is not None), None)
    confirm_heading = next((o.heading for o in rows if o.source_id == (confirm or {}).get("source_id") and o.heading is not None), None)
    heading_delta = _heading_delta(first_heading, confirm_heading)
    opposite = heading_delta is not None and heading_delta >= 120
    return {
        "event_id": event.id,
        "public_code": event.public_code,
        "patrol_state": extra.get("patrol_state") or ("FLEET_CONFIRMED" if confirm else "FIRST_SIGHTING"),
        "status": event.status.value if event.status else None,
        "unique_buses": [row["source_id"] for row in unique],
        "buses": unique,
        "first_sighting": first,
        "confirm": confirm,
        "camera_bays": bays,
        "same_bus_ignored": same_bus_ignored,
        "observation_count": len(rows),
        "clear_passes": clear_passes,
        "repair_passes": list(extra.get("repair_passes") or []),
        "clear_same_bus_ignored": extra.get("clear_same_bus_ignored") or 0,
        "expired_by": extra.get("expired_by") or [],
        "repair_verified_by": extra.get("repair_verified_by") or [],
        "opposite_direction": opposite,
        "heading_delta": heading_delta,
        "usp": "Fleet confirms. One bus cannot.",
        "absence": "Fleet confirms presence. Fleet also confirms absence. One bus can do neither.",
    }


def _heading_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    try:
        delta = abs(float(a) - float(b)) % 360
    except (TypeError, ValueError):
        return None
    return min(delta, 360 - delta)


def _event_observations(db: Session, event_id: str) -> list[Observation]:
    links = db.scalars(select(EventObservation).where(EventObservation.event_id == event_id)).all()
    ids = [lnk.observation_id for lnk in links]
    if not ids:
        return []
    return list(db.scalars(select(Observation).where(Observation.id.in_(ids))).all())


def _reporter_ids(observations: list[Observation]) -> set[str]:
    out: set[str] = set()
    for obs in observations:
        if obs.source_type not in _FLEET_SOURCES or not obs.source_id:
            continue
        if obs.event_type in _CLEAR_PASS_TYPES:
            out.add(obs.source_id)
    return out


def _awaiting_repair_audit(db: Session, event: UrbanEvent) -> bool:
    if event.status in (EventStatus.RE_VERIFICATION, EventStatus.REPAIRED):
        return True
    wos = db.query(WorkOrder).filter(WorkOrder.event_id == event.id).all()
    return any(w.status in (WorkOrderStatus.RE_VERIFICATION, WorkOrderStatus.COMPLETED) for w in wos)


def _event_ref_ts(event: UrbanEvent) -> datetime:
    return max(_aware(event.timestamp), _aware(getattr(event, "updated_at", None)))


def _nearby_events(db: Session, lat: float, lon: float, *extra_where):
    settings = get_settings()
    lat_min, lat_max, lon_min, lon_max = bounding_box(lat, lon, settings.fusion_max_distance_meters * 1.5)
    return list(
        db.scalars(
            select(UrbanEvent).where(
                UrbanEvent.status.notin_([EventStatus.REJECTED]),
                UrbanEvent.latitude.between(lat_min, lat_max),
                UrbanEvent.longitude.between(lon_min, lon_max),
                *extra_where,
            )
        ).all()
    )


def _maybe_reopen_after_resense(db: Session, event: UrbanEvent, obs: Observation) -> None:
    extra = dict(event.extra or {})
    if extra.get("patrol_state") != "REPAIR_VERIFIED":
        return
    if obs.event_type not in _REPAIR_TRIGGER_TYPES:
        return
    if obs.source_type not in _FLEET_SOURCES or not obs.source_id:
        return
    bay = ((obs.extra or {}).get("camera_bay") or "").upper()
    if bay == "CABIN":
        return
    prior = {
        o.source_id
        for o in _event_observations(db, event.id)
        if o.id != obs.id and o.source_type in _FLEET_SOURCES and o.source_id
    }
    if obs.source_id in prior:
        return
    event.status = EventStatus.REOPENED
    extra["patrol_state"] = "FLEET_CONFIRMED"
    extra["patrol_note"] = (
        "New independent bus re-sensed after fleet audit. Work order reopened. Not an accusation."
    )
    write_extra(event, extra)
    for wo in db.query(WorkOrder).filter(WorkOrder.event_id == event.id).all():
        if wo.status in (WorkOrderStatus.RESOLVED, WorkOrderStatus.RE_VERIFICATION, WorkOrderStatus.COMPLETED):
            wo.status = WorkOrderStatus.FAILED


def record_clear_passes(
    db: Session,
    *,
    latitude: float | None,
    longitude: float | None,
    source_id: str | None,
    heading: float | None = None,
    camera_bay: str | None = None,
    source_type: SourceType = SourceType.PHONE,
    timestamp: datetime | None = None,
) -> dict:
    """Later independent buses that do not re-trigger: expire a rumour or audit a repair."""
    if latitude is None or longitude is None or not source_id:
        return {"ok": False, "reason": "need gps and source_id"}
    if source_type not in _FLEET_SOURCES:
        return {"ok": False, "reason": "not a fleet source"}
    bay = (camera_bay or "").upper() or None
    if bay == "CABIN":
        return {"ok": True, "skipped": "cabin"}
    try:
        validate_coords(latitude, longitude)
    except Exception:
        return {"ok": False, "reason": "invalid coords"}

    settings = get_settings()
    now = timestamp or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    touched: list[dict] = []

    candidates = _nearby_events(db, latitude, longitude, UrbanEvent.event_type.in_(list(_CLEAR_PASS_TYPES)))

    for event in candidates:
        extra = dict(event.extra or {})
        state = extra.get("patrol_state") or "FIRST_SIGHTING"
        if state in ("EXPIRED", "REPAIR_VERIFIED"):
            continue
        if event.status in (EventStatus.RESOLVED, EventStatus.REOPENED) and state != "FLEET_CONFIRMED":
            if not _awaiting_repair_audit(db, event):
                continue
        dt = abs((now - _event_ref_ts(event)).total_seconds())
        if dt > settings.fusion_max_time_seconds:
            continue
        dist = haversine_m(latitude, longitude, event.latitude, event.longitude)
        if dist > settings.fusion_max_distance_meters:
            continue

        observations = _event_observations(db, event.id)
        reporters = _reporter_ids(observations)
        awaiting = _awaiting_repair_audit(db, event)
        bucket_key = "repair_passes" if awaiting else "clear_passes"
        passes = list(extra.get(bucket_key) or [])
        ignored = int(extra.get("clear_same_bus_ignored") or 0)

        if source_id in reporters:
            extra["clear_same_bus_ignored"] = ignored + 1
            write_extra(event, extra)
            touched.append({"event_id": event.id, "public_code": event.public_code, "ignored": True, "patrol_state": state})
            continue
        if any(row.get("source_id") == source_id for row in passes):
            extra["clear_same_bus_ignored"] = ignored + 1
            write_extra(event, extra)
            touched.append({"event_id": event.id, "public_code": event.public_code, "ignored": True, "patrol_state": state})
            continue

        row = {
            "source_id": source_id,
            "timestamp": now.isoformat(),
            "heading": heading,
            "camera_bay": bay,
            "distance_m": round(dist, 1),
        }
        passes.append(row)
        extra[bucket_key] = passes
        extra["clear_same_bus_ignored"] = ignored
        if not awaiting:
            extra["clear_passes"] = passes
        unique_clear = [item["source_id"] for item in passes]

        if state == "FIRST_SIGHTING" and len(unique_clear) >= settings.clear_pass_expire_after:
            extra["patrol_state"] = "EXPIRED"
            extra["expired_by"] = unique_clear
            extra["patrol_note"] = (
                "Three later buses did not re-sense. Not ground truth. Officer can reopen. "
                "We will not send the ward a one-bus rumour."
            )
            event.status = EventStatus.UNVERIFIED
        elif awaiting and len(unique_clear) >= settings.clear_pass_repair_after:
            extra["patrol_state"] = "REPAIR_VERIFIED"
            extra["repair_verified_by"] = unique_clear
            extra["patrol_note"] = (
                "Two later independent buses did not re-sense after repair. "
                "Fleet audit — not certified asphalt."
            )
            event.status = EventStatus.RESOLVED
            for wo in db.query(WorkOrder).filter(WorkOrder.event_id == event.id).all():
                if wo.status in (WorkOrderStatus.RE_VERIFICATION, WorkOrderStatus.COMPLETED):
                    wo.status = WorkOrderStatus.RESOLVED
        write_extra(event, extra)
        touched.append(
            {
                "event_id": event.id,
                "public_code": event.public_code,
                "ignored": False,
                "patrol_state": extra.get("patrol_state"),
                "clear_pass_count": len(unique_clear),
            }
        )

    if touched:
        db.flush()
    return {"ok": True, "events": touched}


def _stamp_patrol(event: UrbanEvent, observations: list[Observation], incoming: Observation | None = None) -> None:
    fleet = _fleet_ids(observations)
    extra = dict(event.extra or {})
    prev = extra.get("patrol_state")
    extra["confirming_sources"] = fleet

    if prev == "REPAIR_VERIFIED":
        write_extra(event, extra)
        return
    if prev == "EXPIRED" and len(fleet) < 2:
        extra["patrol_state"] = "EXPIRED"
        extra["patrol_note"] = (
            "Three later buses did not re-sense. Not ground truth. Officer can reopen."
        )
        write_extra(event, extra)
        return

    if len(fleet) >= 2:
        extra["patrol_state"] = "FLEET_CONFIRMED"
        extra["patrol_note"] = (
            "A second independent bus/phone reported the same cluster. "
            "Fleet confirm — not inspector ground truth."
        )
        if incoming is not None:
            first_id = fleet[0]
            first_obs = next((o for o in observations if o.source_id == first_id), None)
            delta = _heading_delta(first_obs.heading if first_obs else None, incoming.heading)
            if delta is not None and delta >= 120:
                extra["opposite_direction"] = True
                extra["heading_delta"] = delta
        if event.status == EventStatus.UNVERIFIED:
            event.status = EventStatus.CONFIRMED
    else:
        extra["patrol_state"] = "FIRST_SIGHTING"
        extra["patrol_note"] = "One vehicle reported this. Another bus on the same patch can confirm."
    write_extra(event, extra)


def default_engine() -> FusionEngine:
    return SpatialTemporalFusionEngine()
