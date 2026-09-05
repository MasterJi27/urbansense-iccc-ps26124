from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_schema_columns(db_engine) -> None:
    """Add ward/feed columns on an already-provisioned Azure or SQLite database."""
    dialect = db_engine.url.get_backend_name()
    adds = [
        ("buses", "ward_id", "VARCHAR(36)"),
        ("sensor_nodes", "last_evidence_url", "VARCHAR(512)"),
        ("sensor_nodes", "last_detect_at", "TIMESTAMP"),
        ("sensor_nodes", "patrol_mode", "VARCHAR(16)"),
        ("sensor_nodes", "last_boxes_json", "TEXT"),
        ("sensor_nodes", "person_count", "INTEGER"),
        ("sensor_nodes", "overlay_fps", "FLOAT"),
    ]
    with db_engine.begin() as conn:
        for table, column, coltype in adds:
            try:
                if dialect == "sqlite":
                    cols = [r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
                    if column not in cols:
                        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
                else:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
            except Exception:
                continue


def enable_postgis(db_engine) -> None:
    if db_engine.url.get_backend_name() == "postgresql":
        with db_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()


def ensure_pg_enum_values(db_engine) -> None:
    """Add new EventType / EventStatus labels to an existing Azure Postgres enum."""
    if db_engine.url.get_backend_name() != "postgresql":
        return
    from app.models.event import EventStatus, EventType, SourceType

    groups = (
        ("eventtype", [m.value for m in EventType]),
        ("eventstatus", [m.value for m in EventStatus]),
        ("sourcetype", [m.value for m in SourceType]),
    )
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for type_name, values in groups:
            exists = conn.execute(text("SELECT 1 FROM pg_type WHERE typname = :n"), {"n": type_name}).scalar()
            if not exists:
                continue
            for val in values:
                conn.execute(text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{val}'"))
