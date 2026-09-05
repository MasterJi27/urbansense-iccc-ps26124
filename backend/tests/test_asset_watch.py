from app.models.asset import Asset, AssetCondition, AssetType
from app.services.asset_watch import PASSES_REQUIRED, record_pass
from tests.test_auth import auth_header


def _asset(db, code="SIGN-183", atype=AssetType.TRAFFIC_SIGN, lat=28.6328, lon=77.2195):
    a = Asset(code=code, asset_type=atype, name=code, latitude=lat, longitude=lon,
              qr_payload=f"urbansense://asset/{code}", condition=AssetCondition.GOOD)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_missing_sign_after_repeated_passes(db):
    a = _asset(db)
    for i in range(PASSES_REQUIRED - 1):
        r = record_pass(db, a, 28.6328 + i * 0.00001, 77.2195, observed=False, source_id="BUS-042")
        assert r["raised"] is False
    r = record_pass(db, a, 28.6328, 77.2195, observed=False, source_id="BUS-017")
    assert r["raised"] is True
    assert r["public_code"].startswith("EVENT-")
    from app.models.event import UrbanEvent

    ev = db.get(UrbanEvent, r["event_id"])
    assert ev.event_type.value == "DAMAGED_SIGN"
    assert ev.extra["ai_status"] == "RULE_BASED"
    assert ev.extra["derivation"] == "GIS_ASSET_WATCH"
    assert ev.simulated is False


def test_no_duplicate_while_open(db):
    a = _asset(db, code="SIGN-900")
    for _ in range(PASSES_REQUIRED):
        record_pass(db, a, 28.6328, 77.2195, observed=False, source_id="BUS-042")
    r = record_pass(db, a, 28.6328, 77.2195, observed=False, source_id="BUS-017")
    assert r["raised"] is False
    assert "already covers" in r["reason"]


def test_confirmed_pass_raises_nothing(db):
    a = _asset(db, code="SIGN-901")
    for _ in range(PASSES_REQUIRED - 1):
        record_pass(db, a, 28.6328, 77.2195, observed=False, source_id="BUS-042")
    r = record_pass(db, a, 28.6328, 77.2195, observed=True, source_id="BUS-042")
    assert r["raised"] is False


def test_zebra_and_divider_mappings(db):
    z = _asset(db, code="ZEBRA-1", atype=AssetType.ZEBRA_CROSSING, lat=28.62, lon=77.222)
    for _ in range(PASSES_REQUIRED):
        r = record_pass(db, z, 28.62, 77.222, observed=False, source_id="BUS-001")
    assert r["raised"] is True
    from app.models.event import UrbanEvent

    assert db.get(UrbanEvent, r["event_id"]).event_type.value == "MISSING_ZEBRA"
    d = _asset(db, code="DIV-1", atype=AssetType.DIVIDER, lat=28.624, lon=77.228)
    for _ in range(PASSES_REQUIRED):
        r = record_pass(db, d, 28.624, 77.228, observed=False, source_id="BUS-001")
    assert r["raised"] is True
    assert db.get(UrbanEvent, r["event_id"]).event_type.value == "MISSING_DIVIDER"


def test_unmapped_asset_type_raises_nothing(db):
    a = _asset(db, code="ROAD-1", atype=AssetType.ROAD)
    r = record_pass(db, a, 28.6328, 77.2195, observed=False, source_id="BUS-042")
    assert r["raised"] is False


def test_asset_pass_endpoints(client, admin_token, db):
    _asset(db, code="SIGN-E2E", lat=28.6400, lon=77.2500)
    for _ in range(PASSES_REQUIRED):
        r = client.post("/assets/SIGN-E2E/passes",
                        json={"latitude": 28.6400, "longitude": 77.2500,
                              "observed": False, "source_id": "BUS-042"},
                        headers=auth_header(admin_token))
        assert r.status_code == 200, r.text
    assert r.json()["raised"] is True
    assert r.json()["public_code"].startswith("EVENT-")
    assert r.json()["thresholds"]["passes_required"] == PASSES_REQUIRED
    lst = client.get("/assets/SIGN-E2E/passes", headers=auth_header(admin_token))
    assert lst.status_code == 200 and len(lst.json()) == PASSES_REQUIRED


def test_od_endpoint_lists_trip_pairs(client, admin_token, db):
    from app.models.fleet import Bus, Route, SensorNode, Trip

    route = Route(code="RT-OD", name="OD line", planned_duration_minutes=40,
                  simulated=True, polyline="28.61,77.21;28.63,77.24")
    db.add(route)
    db.flush()
    bus = db.query(Bus).first() or Bus(code="BUS-OD", qr_payload="urbansense://bus/BUS-OD")
    if not bus.id:
        db.add(bus)
        db.flush()
    node = db.query(SensorNode).first()
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    db.add(Trip(bus_id=bus.id, sensor_id=node.id if node else None, route_id=route.id,
                started_at=now, ended_at=now, actual_duration_minutes=44.0, simulated=True))
    db.commit()
    r = client.get("/analytics/od", headers=auth_header(admin_token))
    assert r.status_code == 200
    rows = [x for x in r.json() if x["route_code"] == "RT-OD"]
    assert rows and rows[0]["trips"] >= 1
    assert rows[0]["origin"] == "28.61,77.21"
    assert rows[0]["destination"] == "28.63,77.24"
    assert rows[0]["simulated"] is True
