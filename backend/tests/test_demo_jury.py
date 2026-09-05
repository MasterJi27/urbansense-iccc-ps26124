from tests.test_auth import auth_header


def test_demo_pothole_pair_fleet_confirms(client, admin_token):
    a = client.post("/demo/start", json={"step": "pothole_a"}, headers=auth_header(admin_token))
    b = client.post("/demo/start", json={"step": "pothole_b"}, headers=auth_header(admin_token))
    assert a.status_code == 200 and b.status_code == 200, a.text + b.text
    assert a.json()["event_id"] == b.json()["event_id"]
    assert b.json()["patrol_state"] == "FLEET_CONFIRMED"
    ev = client.get(f"/events/{b.json()['event_id']}", headers=auth_header(admin_token)).json()
    assert ev["status"] == "CONFIRMED"
    assert ev["extra"]["patrol_state"] == "FLEET_CONFIRMED"
    ledger = client.get(f"/events/{ev['id']}/ledger", headers=auth_header(admin_token))
    assert ledger.status_code == 200, ledger.text
    body = ledger.json()
    assert body["unique_buses"] == ["BUS-042", "BUS-017"]
    assert body["first_sighting"]["source_id"] == "BUS-042"
    assert body["confirm"]["source_id"] == "BUS-017"
    assert body["usp"] == "Fleet confirms. One bus cannot."


def test_jury_run_covers_ps_lines(client, admin_token):
    r = client.post("/demo/jury-run", headers=auth_header(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    steps = body["steps"]
    assert len(steps) >= 5
    lines = " ".join(s["ps_line"] for s in steps)
    assert "first sighting" in lines.lower()
    assert "fleet-confirm" in lines.lower()
    assert "SIGN-183" in lines
    assert "Congestion" in lines
    assert "plate" in lines.lower()
    assert "Cabin" in lines
    assert "expired" in lines.lower()
    assert "Repair verified" in lines
    pothole = next(s for s in steps if "fleet-confirm" in s["ps_line"].lower())
    assert pothole["patrol_state"] == "FLEET_CONFIRMED"
    cabin = next(s for s in steps if "Cabin" in s["ps_line"])
    assert cabin["event_type"] != "POTHOLE"
    assert cabin.get("camera_bay") == "CABIN"
    water = next(s for s in steps if "Waterlogging" in s["ps_line"])
    ev = client.get(f"/events/{water['event_id']}", headers=auth_header(admin_token)).json()
    assert ev["event_type"] == "WATERLOGGING"
    assert ev["extra"]["engine_status"] == "SIMULATED"
    rash = next(s for s in steps if "plate" in s["ps_line"].lower())
    detail = client.get(f"/events/{rash['event_id']}", headers=auth_header(admin_token)).json()
    plates = [o.get("plate_text") for o in detail.get("observations") or [] if o.get("plate_text")]
    assert plates
