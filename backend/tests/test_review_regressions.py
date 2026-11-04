"""Regressions for the confirmed code-review findings."""

import asyncio
import io
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api.routes import cameras as cameras_routes
from app.api.routes import ingest as ingest_routes
from app.api.routes import perception as perception_routes
from app.api.routes import work_orders as wo_routes
from app.config import get_settings
from app.models.event import EventObservation, EventStatus, EventType, Observation, Severity, SourceType, UrbanEvent
from app.models.fleet import SensorNode
from app.models.work_order import WorkOrder
from app.services import rdd_cloud
from app.services.bbox_severity import severity_for_detection
from app.services.fusion import SpatialTemporalFusionEngine, _free_event_code, _new_event_from_obs
from app.services.rate_limit import client_ip
from tests.conftest import TestingSession
from tests.test_auth import auth_header

JPEG = b"\xff\xd8\xff\xd9" + b"review-regression"


def _request(*xff_lines: str, peer: str = "10.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-forwarded-for", line.encode()) for line in xff_lines],
            "client": (peer, 5000),
        }
    )


@pytest.fixture
def proxy_hops(monkeypatch):
    def _set(hops):
        monkeypatch.setattr(get_settings(), "trusted_proxy_hops", hops)

    return _set


# 1. client_ip trusted the first X-Forwarded-For value, which the caller controls.


def test_client_ip_takes_rightmost_trusted_hop(proxy_hops):
    proxy_hops(1)
    assert client_ip(_request("6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    assert client_ip(_request("1.1.1.1, 2.2.2.2, 203.0.113.9")) == "203.0.113.9"


def test_client_ip_counts_configured_proxy_hops(proxy_hops):
    proxy_hops(2)
    assert client_ip(_request("6.6.6.6, 203.0.113.9, 10.9.9.9")) == "203.0.113.9"


def test_client_ip_reads_every_forwarded_header_line(proxy_hops):
    proxy_hops(1)
    assert client_ip(_request("6.6.6.6", "203.0.113.9")) == "203.0.113.9"


def test_client_ip_drops_azure_port_suffix(proxy_hops):
    proxy_hops(1)
    assert client_ip(_request("6.6.6.6, 203.0.113.9:51234")) == "203.0.113.9"
    assert client_ip(_request("6.6.6.6, [2001:db8::1]:51234")) == "2001:db8::1"
    assert client_ip(_request("6.6.6.6, 2001:db8::1")) == "2001:db8::1"


def test_client_ip_ignores_header_when_no_proxy_is_trusted(proxy_hops):
    proxy_hops(0)
    assert client_ip(_request("6.6.6.6", peer="198.51.100.4")) == "198.51.100.4"


def test_client_ip_short_chain_falls_back_to_socket_peer(proxy_hops):
    proxy_hops(2)
    assert client_ip(_request("6.6.6.6", peer="198.51.100.4")) == "198.51.100.4"
    assert client_ip(_request(peer="198.51.100.4")) == "198.51.100.4"


def test_trusted_hops_default_follows_environment():
    from app.config import Settings

    assert Settings(app_env="development", trusted_proxy_hops=None).effective_trusted_proxy_hops == 0
    assert Settings(app_env="production", trusted_proxy_hops=None).effective_trusted_proxy_hops == 1
    assert Settings(app_env="production", trusted_proxy_hops=3).effective_trusted_proxy_hops == 3


def test_field_join_pin_lockout_survives_rotating_forwarded_for(client, admin_token, proxy_hops):
    proxy_hops(1)
    codes = []
    for n in range(30):
        # Azure appends the real peer last; everything before it is whatever the caller sent.
        r = client.post("/auth/field-join", json={"code": "000000"}, headers={"X-Forwarded-For": f"10.1.1.{n}, 203.0.113.9"})
        codes.append(r.status_code)
    assert codes[0] == 401
    assert 429 in codes, codes
    assert codes.index(429) <= 10


def test_login_limiter_survives_rotating_forwarded_for(client, admin_token, proxy_hops):
    proxy_hops(1)
    codes = [
        client.post(
            "/auth/login",
            json={"email": "admin@test.local", "password": "wrong-password"},
            headers={"X-Forwarded-For": f"10.3.3.{n}, 203.0.113.10"},
        ).status_code
        for n in range(12)
    ]
    assert codes[0] == 401
    assert 429 in codes, codes


def test_field_join_lockout_without_trusted_proxy_ignores_header(client, admin_token, proxy_hops):
    proxy_hops(0)
    codes = [
        client.post("/auth/field-join", json={"code": "000000"}, headers={"X-Forwarded-For": f"10.4.4.{n}"}).status_code
        for n in range(30)
    ]
    assert 429 in codes, codes


# 2-4. Work orders.


def _event_id(client, token, lat=28.6101, lon=77.2101) -> str:
    r = client.post(
        "/observations",
        json={
            "event_type": "ROAD_DAMAGE",
            "latitude": lat,
            "longitude": lon,
            "source_type": "PHONE",
            "source_id": "NODE-X",
            "confidence": 0.7,
            "simulated": True,
        },
        headers=auth_header(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["event"]["id"]


def _make_wo(client, token, title="Fix", event_id=None) -> dict:
    r = client.post("/work-orders", json={"title": title, "event_id": event_id}, headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_patch_work_order_by_public_code(client, admin_token):
    wo = _make_wo(client, admin_token)
    assert client.get(f"/work-orders/{wo['public_code']}", headers=auth_header(admin_token)).status_code == 200
    r = client.patch(f"/work-orders/{wo['public_code']}", json={"title": "Renamed"}, headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == wo["id"]
    assert r.json()["title"] == "Renamed"
    assert client.patch("/work-orders/WO-999", json={"title": "x"}, headers=auth_header(admin_token)).status_code == 404


@pytest.mark.parametrize("status", ["RESOLVED", "FAILED"])
def test_patch_cannot_close_work_order_behind_the_events_back(client, admin_token, status):
    event_id = _event_id(client, admin_token)
    wo = _make_wo(client, admin_token, event_id=event_id)
    r = client.patch(f"/work-orders/{wo['id']}", json={"status": status}, headers=auth_header(admin_token))
    assert r.status_code == 400
    assert "/verify" in r.json()["detail"]
    assert client.get(f"/work-orders/{wo['id']}", headers=auth_header(admin_token)).json()["status"] == "PENDING"
    db = TestingSession()
    try:
        assert db.get(UrbanEvent, event_id).status == EventStatus.ASSIGNED
    finally:
        db.close()


def test_patch_still_allows_working_states_and_verify_closes_event(client, admin_token):
    event_id = _event_id(client, admin_token)
    wo = _make_wo(client, admin_token, event_id=event_id)
    r = client.patch(f"/work-orders/{wo['public_code']}", json={"status": "IN_PROGRESS"}, headers=auth_header(admin_token))
    assert r.status_code == 200 and r.json()["status"] == "IN_PROGRESS"
    done = client.post(
        f"/work-orders/{wo['public_code']}/verify", json={"passed": True, "notes": "ok"}, headers=auth_header(admin_token)
    )
    assert done.json()["status"] == "RESOLVED"
    assert client.get(f"/events/{event_id}", headers=auth_header(admin_token)).json()["status"] == "RESOLVED"


def test_work_order_code_does_not_collide_after_delete(client, admin_token, db):
    codes = [_make_wo(client, admin_token, title=f"WO {n}")["public_code"] for n in range(3)]
    assert codes == ["WO-001", "WO-002", "WO-003"]
    db.query(WorkOrder).filter(WorkOrder.public_code == "WO-001").delete()
    db.commit()
    # count()+1 would hand out WO-003 again and 500 on the unique index.
    assert _make_wo(client, admin_token, title="after delete")["public_code"] == "WO-004"


def test_work_order_code_orders_numerically_past_999(client, admin_token, db):
    for n in (998, 999, 1000):
        db.add(WorkOrder(public_code=f"WO-{n:03d}", title="seed", qr_payload=f"urbansense://work-order/WO-{n:03d}"))
    db.commit()
    assert _make_wo(client, admin_token)["public_code"] == "WO-1001"


def test_work_order_create_retries_when_it_loses_the_code_race(client, admin_token, monkeypatch):
    _make_wo(client, admin_token)  # WO-001 exists
    real = wo_routes._next_code
    calls = []

    def stale_then_real(db):
        calls.append(1)
        return "WO-001" if len(calls) == 1 else real(db)

    monkeypatch.setattr(wo_routes, "_next_code", stale_then_real)
    made = _make_wo(client, admin_token, title="racer")
    assert len(calls) == 2
    assert made["public_code"] == "WO-002"
    db = TestingSession()
    try:
        assert len(db.scalars(select(WorkOrder)).all()) == 2
    finally:
        db.close()


# 5. Severity must grow with box area, on every RDD route.

_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


def _det(area: float, class_severity: str = "HIGH") -> dict:
    side = area**0.5
    return {
        "klass": "Pothole",
        "class_id": "D40",
        "confidence": 0.8,
        "bbox": [0.3, 0.3, round(0.3 + side, 4), round(0.3 + side, 4)],
        "event_type": "POTHOLE",
        "severity": class_severity,
    }


def test_severity_is_monotonic_in_box_area():
    areas = [0.00001, 0.001, 0.01, 0.04, 0.05, 0.08, 0.11, 0.12, 0.2, 0.4]
    ranks = [_RANK[severity_for_detection(_det(a))["severity"]] for a in areas]
    assert ranks == sorted(ranks), ranks
    # The reported case: 1% of the frame was HIGH while 8% was MEDIUM.
    small = severity_for_detection(_det(0.01))["severity"]
    medium = severity_for_detection(_det(0.08))["severity"]
    assert _RANK[small] <= _RANK[medium]
    assert (small, medium) == (Severity.LOW, Severity.MEDIUM)


def test_severity_uses_class_default_only_without_a_box():
    assert severity_for_detection({"severity": "HIGH"})["severity"] == Severity.HIGH
    assert severity_for_detection({"bbox": [0.5, 0.5, 0.5, 0.5], "severity": "MEDIUM"})["severity"] == Severity.MEDIUM
    assert severity_for_detection({})["severity"] == Severity.MEDIUM
    # A sliver rounds to bbox_frac 0.0 but still has area, so it must not jump back to the class default.
    assert severity_for_detection({"bbox": [0.1, 0.1, 0.1005, 0.1005], "severity": "HIGH"})["severity"] == Severity.LOW


def test_ingest_and_analyze_frame_grade_the_same_box_the_same(client, admin_token, db, tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path))
    get_settings.cache_clear()
    current = {}
    monkeypatch.setattr(ingest_routes, "detect_rdd", lambda _data: {"ok": True, "detections": [current["det"]]})
    monkeypatch.setattr(perception_routes, "detect_rdd", lambda _data: {"ok": True, "detections": [current["det"]]})

    seen = []
    for i, area in enumerate((0.01, 0.08, 0.25)):
        current["det"] = _det(area)
        lat = 28.60 + 0.01 * i
        field = client.post(
            "/ingest/phone/still",
            headers=auth_header(admin_token),
            files={"file": ("a.jpg", JPEG, "image/jpeg")},
            data={"gps_accuracy": "8", "latitude": str(lat), "longitude": "77.20", "source_id": f"FIELD-{i}"},
        )
        assert field.status_code == 200, field.text
        frame = client.post(
            "/ai/analyze-frame",
            headers=auth_header(admin_token),
            files={"file": ("a.jpg", JPEG, "image/jpeg")},
            data={"latitude": str(lat + 0.005), "longitude": "77.25", "source_id": f"FRAME-{i}", "source_type": "PHONE"},
        )
        assert frame.status_code == 200, frame.text
        code = frame.json()["items"][0]["event"]
        frame_sev = db.query(UrbanEvent).filter(UrbanEvent.public_code == code).one().severity.value
        seen.append((field.json()["event"]["severity"], frame_sev))
    assert seen == [("LOW", "LOW"), ("MEDIUM", "MEDIUM"), ("HIGH", "HIGH")]


# 6. Fusion: exact match, event code, and what an IntegrityError means.


def _stored_event(db, lat, lon, code):
    obs = Observation(
        id=f"{code[-6:].lower()}00-0000-4000-8000-000000000000",
        event_type=EventType.POTHOLE,
        severity=Severity.MEDIUM,
        latitude=lat,
        longitude=lon,
        timestamp=datetime.now(timezone.utc),
        source_type=SourceType.PHONE,
        source_id=f"SRC-{code}",
        confidence=0.6,
        simulated=False,
        extra={"payload_kind": "FIELD"},
    )
    db.add(obs)
    db.flush()
    event = _new_event_from_obs(obs, code)
    db.add(event)
    db.flush()
    db.add(EventObservation(event_id=event.id, observation_id=obs.id, distance_m=0))
    db.flush()
    return event


@pytest.mark.parametrize("exact_first", [True, False])
def test_fusion_keeps_an_exact_zero_metre_match(db, exact_first):
    lat, lon = 28.6100, 77.2100
    near = (lat, lon + 0.0001)  # ~10 m east
    if exact_first:
        exact = _stored_event(db, lat, lon, "EVENT-AAAAAA")
        far = _stored_event(db, *near, "EVENT-BBBBBB")
    else:
        far = _stored_event(db, *near, "EVENT-BBBBBB")
        exact = _stored_event(db, lat, lon, "EVENT-AAAAAA")
    incoming = Observation(
        event_type=EventType.POTHOLE,
        severity=Severity.MEDIUM,
        latitude=lat,
        longitude=lon,
        timestamp=datetime.now(timezone.utc),
        source_type=SourceType.PHONE,
        source_id="SRC-NEW",
        confidence=0.7,
        simulated=False,
        extra={"payload_kind": "FIELD"},
    )
    db.add(incoming)
    db.flush()
    result = SpatialTemporalFusionEngine().fuse(db, incoming)
    assert result.created is False
    assert result.event.id == exact.id
    assert result.distance_m == 0.0
    assert far.id != result.event.id


def test_event_code_is_lengthened_when_taken(db):
    assert _free_event_code(db, "abcdef12-3456-4000-8000-000000000000") == "EVENT-ABCDEF"
    _stored_event(db, 28.61, 77.21, "EVENT-ABCDEF")
    assert _free_event_code(db, "abcdef12-3456-4000-8000-000000000000") == "EVENT-ABCDEF12"
    _stored_event(db, 28.62, 77.22, "EVENT-ABCDEF12")
    assert _free_event_code(db, "abcdef12-3456-4000-8000-000000000000") == "EVENT-ABCDEF1234"


def test_many_first_sightings_get_distinct_event_codes(client, admin_token):
    codes = set()
    for i in range(25):
        r = client.post(
            "/observations",
            json={
                "event_type": "POTHOLE",
                "latitude": 28.50 + 0.01 * i,
                "longitude": 77.10,
                "source_type": "PHONE",
                "source_id": f"NODE-{i}",
                "confidence": 0.6,
                "simulated": True,
            },
            headers=auth_header(admin_token),
        )
        assert r.status_code == 200, r.text
        codes.add(r.json()["event"]["public_code"])
    assert len(codes) == 25


def _phone_body(**over) -> dict:
    body = {
        "event_type": "POTHOLE",
        "latitude": 28.61,
        "longitude": 77.21,
        "source_type": "PHONE",
        "source_id": "NODE-IT",
        "confidence": 0.6,
        "simulated": False,
    }
    body.update(over)
    return body


def _integrity(message: str) -> IntegrityError:
    return IntegrityError("INSERT INTO events", {}, Exception(message))


def test_event_code_collision_is_retried_not_blamed_on_the_bus(client, admin_token, monkeypatch):
    real = ingest_routes.ingest_observation
    calls = []

    def flaky(db, payload, actor_id=None, engine=None):
        calls.append(1)
        if len(calls) == 1:
            raise _integrity("UNIQUE constraint failed: events.public_code")
        return real(db, payload, actor_id=actor_id, engine=engine)

    monkeypatch.setattr(ingest_routes, "ingest_observation", flaky)
    r = client.post("/ingest/phone", json=_phone_body(), headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    assert len(calls) == 2


def test_persistent_event_code_collision_is_a_conflict_not_a_bus_error(client, admin_token, monkeypatch):
    def always(*_a, **_k):
        raise _integrity('duplicate key value violates unique constraint "ix_events_public_code"')

    monkeypatch.setattr(ingest_routes, "ingest_observation", always)
    r = client.post("/ingest/phone", json=_phone_body(), headers=auth_header(admin_token))
    assert r.status_code == 409
    assert "Bus/source" not in r.json()["detail"]


def test_real_foreign_key_failure_still_reports_the_bus_link(client, admin_token, monkeypatch):
    def fk(*_a, **_k):
        raise _integrity('insert or update violates foreign key constraint "observations_bus_id_fkey"')

    monkeypatch.setattr(ingest_routes, "ingest_observation", fk)
    r = client.post("/ingest/phone", json=_phone_body(), headers=auth_header(admin_token))
    assert r.status_code == 400
    assert "Bus/source link" in r.json()["detail"]


# 7. A field-booth PIN token may add a camera, never rewrite a node it did not create.


def _field_token(client, admin_token) -> str:
    code = client.post("/auth/field-booth", json={"bus_code": "BUS-017"}, headers=auth_header(admin_token)).json()["code"]
    return client.post("/auth/field-join", json={"code": code}).json()["access_token"]


@pytest.mark.parametrize("code", ["NODE-001", "node-001", "node 001"])
def test_field_token_cannot_rewrite_an_existing_node(client, admin_token, db, code):
    token = _field_token(client, admin_token)
    r = client.post(
        "/cameras",
        headers=auth_header(token),
        json={"code": code, "vendor": "CP_PLUS", "bay": "FRONT", "bus_code": "BUS-042", "label": "HIJACKED"},
    )
    assert r.status_code == 403, r.text
    node = db.query(SensorNode).filter(SensorNode.code == "NODE-001").one()
    assert node.source_type == "PHONE"
    assert node.device_label == "PHONE"
    assert node.bus_id is None


def test_field_token_registers_a_new_camera_once(client, admin_token):
    token = _field_token(client, admin_token)
    body = {"code": "CAM-FIELD-77", "vendor": "BROWSER", "bay": "FRONT"}
    assert client.post("/cameras", headers=auth_header(token), json=body).status_code == 200
    assert client.post("/cameras", headers=auth_header(token), json=body).status_code == 403


def test_officer_can_still_update_an_existing_node(client, admin_token, db):
    r = client.post(
        "/cameras",
        headers=auth_header(admin_token),
        json={"code": "NODE-001", "vendor": "CP_PLUS", "bay": "FRONT", "bus_code": "BUS-042"},
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    node = db.query(SensorNode).filter(SensorNode.code == "NODE-001").one()
    assert node.source_type == "BUS_CCTV"
    assert node.bus_id is not None


# 8. Blocking work must not run on the event loop.


def _on_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.fixture
def loop_probe(monkeypatch):
    """Replace every slow call the routes make with a stub that records whether it ran on the event loop."""
    seen: dict[str, list[bool]] = {}

    def stub(name, result):
        def call(*_a, **_k):
            seen.setdefault(name, []).append(_on_loop())
            return result

        return call

    saved = stub("save_evidence_bytes", "http://localhost:8000/evidence/probe.jpg")
    safe = stub("screen_still", {"ok": True, "ai_status": "DISABLED", "skipped": True})
    rdd = stub("detect_rdd", {"ok": True, "detections": []})
    snap = stub("fetch_snapshot", JPEG)
    monkeypatch.setattr(ingest_routes, "save_evidence_bytes", saved)
    monkeypatch.setattr(ingest_routes, "screen_still", safe)
    monkeypatch.setattr(ingest_routes, "detect_rdd", rdd)
    monkeypatch.setattr(perception_routes, "save_evidence_bytes", saved)
    monkeypatch.setattr(perception_routes, "detect_rdd", rdd)
    monkeypatch.setattr(cameras_routes, "fetch_snapshot", snap)

    real_ingest = ingest_routes.ingest_observation

    def watched_ingest(*a, **k):
        seen.setdefault("ingest_observation", []).append(_on_loop())
        return real_ingest(*a, **k)

    monkeypatch.setattr(ingest_routes, "ingest_observation", watched_ingest)
    real_frame_ingest = perception_routes.ingest_observation

    def watched_frame_ingest(*a, **k):
        seen.setdefault("frame_ingest_observation", []).append(_on_loop())
        return real_frame_ingest(*a, **k)

    monkeypatch.setattr(perception_routes, "ingest_observation", watched_frame_ingest)
    return seen


def _assert_off_loop(seen, *names):
    for name in names:
        assert seen.get(name), f"{name} never ran"
        assert not any(seen[name]), f"{name} ran on the event loop"


def test_phone_still_blocking_work_is_off_the_event_loop(client, admin_token, loop_probe):
    clip = b"\x1a\x45\xdf\xa3" + b"webm-clip"
    r = client.post(
        "/ingest/phone/still",
        headers=auth_header(admin_token),
        files={"file": ("a.jpg", JPEG, "image/jpeg"), "clip": ("c.webm", clip, "video/webm")},
        data={"gps_accuracy": "8", "latitude": "28.61", "longitude": "77.21", "source_id": "FIELD-LOOP"},
    )
    assert r.status_code == 200, r.text
    _assert_off_loop(loop_probe, "screen_still", "save_evidence_bytes", "ingest_observation")
    assert len(loop_probe["save_evidence_bytes"]) == 2  # still and clip


def test_cctv_still_and_bus_frame_blocking_work_is_off_the_event_loop(client, admin_token, loop_probe):
    for path, source in (("/ingest/cctv/still", "CAM-LOOP"), ("/ingest/bus/stream-frame", "BUS-042-FRONT")):
        loop_probe.clear()
        r = client.post(
            path,
            headers=auth_header(admin_token),
            files={"file": ("a.jpg", JPEG, "image/jpeg")},
            data={"source_id": source},
        )
        assert r.status_code == 200, r.text
        _assert_off_loop(loop_probe, "screen_still", "save_evidence_bytes", "ingest_observation")


def test_probe_blocking_work_is_off_the_event_loop(client, admin_token, loop_probe):
    r = client.post("/ingest/phone/probe", headers=auth_header(admin_token), files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert r.status_code == 200, r.text
    _assert_off_loop(loop_probe, "screen_still", "detect_rdd")


def test_camera_pull_blocking_work_is_off_the_event_loop(client, admin_token, loop_probe):
    r = client.post(
        "/cameras/pull",
        headers=auth_header(admin_token),
        json={"snapshot_url": "http://192.168.1.64/snap.jpg", "code": "CAM-PULL-LOOP"},
    )
    assert r.status_code == 200, r.text
    _assert_off_loop(loop_probe, "fetch_snapshot", "screen_still", "save_evidence_bytes", "ingest_observation")


def test_analyze_frame_blocking_work_is_off_the_event_loop(client, admin_token, loop_probe, monkeypatch):
    monkeypatch.setattr(perception_routes, "detect_rdd", lambda _d: (loop_probe.setdefault("detect_rdd", []).append(_on_loop()), {"ok": True, "detections": [_det(0.1)]})[1])
    r = client.post(
        "/ai/analyze-frame",
        headers=auth_header(admin_token),
        files={"file": ("a.jpg", JPEG, "image/jpeg")},
        data={"latitude": "28.61", "longitude": "77.21", "source_id": "FRAME-LOOP", "source_type": "PHONE"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1
    _assert_off_loop(loop_probe, "save_evidence_bytes", "detect_rdd", "frame_ingest_observation")


# 10. rdd_cloud: EXIF orientation, no cached None session, no dead branch.


def _exif_jpeg(width: int, height: int, orientation: int) -> bytes:
    img = Image.new("RGB", (width, height), (90, 90, 90))
    exif = Image.Exif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


class _FakeSession:
    def get_inputs(self):
        return [SimpleNamespace(name="images")]

    def run(self, _outputs, _feed):
        import numpy as np

        return [np.zeros((1, 8, 10), dtype=np.float32)]


@pytest.fixture
def fake_rdd_session(monkeypatch):
    monkeypatch.setattr(rdd_cloud, "_SESSION", None)
    monkeypatch.setattr(
        rdd_cloud,
        "rdd_cloud_status",
        lambda: {"evaluated": True, "honesty": "REAL", "model": "m", "provider": "p", "note": ""},
    )
    monkeypatch.setattr(rdd_cloud, "_session", lambda: _FakeSession())
    dims = []
    real_decode = rdd_cloud._decode

    def spy(raw, orig_w, orig_h, *rest):
        dims.append((orig_w, orig_h))
        return real_decode(raw, orig_w, orig_h, *rest)

    monkeypatch.setattr(rdd_cloud, "_decode", spy)
    return dims


def test_rdd_reads_exif_rotation_before_inference(fake_rdd_session):
    out = rdd_cloud.detect_rdd(_exif_jpeg(200, 100, orientation=6))  # stored landscape, shown portrait
    assert out["ok"] is True
    assert fake_rdd_session == [(100, 200)]


def test_rdd_leaves_upright_stills_alone(fake_rdd_session):
    rdd_cloud.detect_rdd(_exif_jpeg(200, 100, orientation=1))
    assert fake_rdd_session == [(200, 100)]


def test_rdd_empty_result_still_reports_real(fake_rdd_session):
    out = rdd_cloud.detect_rdd(_exif_jpeg(64, 64, orientation=1))
    assert out["detections"] == []
    assert out["ai_status"] == "REAL"


def test_rdd_missing_model_is_not_cached_forever(monkeypatch, tmp_path):
    weights = tmp_path / "rdd_india.onnx"
    created = []

    class FakeOrt:
        class SessionOptions:
            pass

        @staticmethod
        def InferenceSession(path, opts, providers):
            created.append(path)
            return _FakeSession()

    monkeypatch.setattr(rdd_cloud, "_SESSION", None)
    monkeypatch.setattr(rdd_cloud, "ort", FakeOrt)
    monkeypatch.setattr(rdd_cloud, "weights_path", lambda: weights)
    assert rdd_cloud._session() is None  # weights not deployed yet
    weights.write_bytes(b"onnx")
    first = rdd_cloud._session()
    assert first is not None  # lru_cache would have kept returning None
    assert rdd_cloud._session() is first
    assert len(created) == 1
