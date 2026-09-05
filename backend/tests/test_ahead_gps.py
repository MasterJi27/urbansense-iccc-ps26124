from app.geo import haversine_m, offset_by_heading
from app.models.event import EventType
from app.services.ahead_gps import ahead_meters_from_bbox, project_ahead
from app.services.imu_rules import shake_event_type


def test_offset_north_moves_latitude():
    lat, lon = offset_by_heading(28.6328, 77.2195, 0, 40)
    assert lat > 28.6328
    assert abs(haversine_m(28.6328, 77.2195, lat, lon) - 40) < 0.6


def test_near_box_is_closer_than_horizon_box():
    near = ahead_meters_from_bbox([0.4, 0.72, 0.6, 0.95])
    far = ahead_meters_from_bbox([0.4, 0.38, 0.55, 0.48])
    assert near < far
    assert 8 <= near <= 25
    assert far >= 30


def test_project_ahead_requires_heading():
    pin = project_ahead(28.63, 77.21, None, [0.2, 0.5, 0.4, 0.9])
    assert pin["used"] is False
    assert pin["latitude"] == 28.63


def test_project_ahead_walks_east():
    pin = project_ahead(28.63, 77.21, 90, [0.2, 0.7, 0.4, 0.92])
    assert pin["used"] is True
    assert pin["longitude"] > 77.21
    assert pin["honesty"] == "RULE_BASED"


def test_shake_is_pothole_unless_fast():
    assert shake_event_type(18, 20, has_box=False) == EventType.POTHOLE
    assert shake_event_type(18, 50, has_box=False) == EventType.RASH_DRIVING
    assert shake_event_type(18, 50, has_box=True) is None
    assert shake_event_type(4, 60, has_box=False) is None
