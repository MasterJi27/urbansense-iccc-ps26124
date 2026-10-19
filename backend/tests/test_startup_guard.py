"""Startup behaviour: the lifespan hook runs on_startup, and a missing database is never papered over in production."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.main as main


def _unreachable(*_args, **_kwargs):
    raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_lifespan_runs_on_startup(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "on_startup", lambda: calls.append("startup"))
    with TestClient(main.app) as c:
        assert c.get("/health").status_code == 200
    assert calls == ["startup"]


def test_production_does_not_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setattr(main.settings, "app_env", "production")
    monkeypatch.setattr(main, "enable_postgis", _unreachable)
    with pytest.raises(OperationalError):
        main.on_startup()


def test_development_still_falls_back_to_a_local_sqlite_file(monkeypatch, tmp_path):
    # Same behaviour as before for the local demo. Run from a temp dir so no urbansense.db lands in the repo.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main.settings, "app_env", "development")
    monkeypatch.setattr(main.settings, "demo_seed_on_start", False)
    monkeypatch.setattr(main, "enable_postgis", _unreachable)
    monkeypatch.setattr(main, "warmup_rdd", lambda: None)
    saved = (main.engine, main.SessionLocal)
    try:
        main.on_startup()
        assert str(main.engine.url).startswith("sqlite")
    finally:
        main.engine, main.SessionLocal = saved
        import app.database as database

        database.engine, database.SessionLocal = saved
