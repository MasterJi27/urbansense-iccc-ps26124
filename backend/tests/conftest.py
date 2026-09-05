import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite://"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEMO_SEED_ON_START"] = "false"

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

get_settings.cache_clear()

from app.database import Base, get_db
from app.main import app
from app.models.fleet import Bus, SensorNode
from app.models.user import User, UserRole
from app.security import hash_password

engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset_db():
    """Each test gets an empty schema so DEMO_LAT fusion cannot pick up leftover events."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def override_db():
    db = TestingSession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db


@pytest.fixture
def db():
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_token(client):
    db = TestingSession()
    if not db.query(User).filter(User.email == "admin@test.local").first():
        db.add(
            User(
                email="admin@test.local",
                full_name="Admin",
                hashed_password=hash_password("password12"),
                role=UserRole.ADMIN,
            )
        )
        db.add(
            User(
                email="op@test.local",
                full_name="Op",
                hashed_password=hash_password("password12"),
                role=UserRole.OPERATOR,
            )
        )
        db.add(Bus(code="BUS-042", registration="DL1", qr_payload="urbansense://bus/BUS-042"))
        db.add(SensorNode(code="NODE-001"))
        db.commit()
    db.close()
    r = client.post("/auth/login", json={"email": "admin@test.local", "password": "password12"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
