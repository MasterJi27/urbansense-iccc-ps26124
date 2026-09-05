"""Accelerometer spike rules. Phone proximity is near/far — it does not measure shake."""

from __future__ import annotations

from app.models.event import EventType

SHAKE_MAG = 16.0
RASH_KMH = 45.0


def shake_event_type(imu_mag: float | None, speed_kmh: float | None, *, has_box: bool) -> EventType | None:
    if has_box or imu_mag is None or imu_mag < SHAKE_MAG:
        return None
    if speed_kmh is not None and speed_kmh >= RASH_KMH:
        return EventType.RASH_DRIVING
    return EventType.POTHOLE
