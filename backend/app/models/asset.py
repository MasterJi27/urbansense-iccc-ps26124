from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utcnow, uuid_str


class AssetType(str, Enum):
    ROAD = "ROAD"
    BUS_STOP = "BUS_STOP"
    TRAFFIC_SIGNAL = "TRAFFIC_SIGNAL"
    TRAFFIC_SIGN = "TRAFFIC_SIGN"
    STREETLIGHT = "STREETLIGHT"
    BRIDGE = "BRIDGE"
    FLYOVER = "FLYOVER"
    DRAIN = "DRAIN"
    DIVIDER = "DIVIDER"
    ZEBRA_CROSSING = "ZEBRA_CROSSING"


class AssetCondition(str, Enum):
    UNKNOWN = "UNKNOWN"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    MISSING = "MISSING"
    DAMAGED = "DAMAGED"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    asset_type: Mapped[AssetType] = mapped_column(SAEnum(AssetType), index=True)
    name: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    qr_payload: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    condition: Mapped[AssetCondition] = mapped_column(SAEnum(AssetCondition), default=AssetCondition.UNKNOWN)
    health_score: Mapped[float] = mapped_column(Float, default=70.0)
    # Bridge/Flyover SHM extension (26124.5) — crowd vibration health, kept nullable for existing assets
    span_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    shm_baseline_rms: Mapped[float | None] = mapped_column(Float, nullable=True)
    shm_last_rms: Mapped[float | None] = mapped_column(Float, nullable=True)
    shm_baseline_freq: Mapped[float | None] = mapped_column(Float, nullable=True)
    shm_last_freq: Mapped[float | None] = mapped_column(Float, nullable=True)
    shm_anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    shm_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    predicted_days_to_maintenance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    inspections = relationship("Inspection", back_populates="asset")


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    inspector_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    condition: Mapped[AssetCondition] = mapped_column(SAEnum(AssetCondition), default=AssetCondition.UNKNOWN)
    checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    asset = relationship("Asset", back_populates="inspections")


class AssetPass(Base):
    """One bus-camera pass by an expected infrastructure asset.

    ``observed`` = the expected object was visually confirmed on this pass.
    Repeated non-confirming passes near the asset raise a GIS-derived
    possible-missing/damaged event (see services.asset_watch). This is
    RULE_BASED/GIS_DERIVED — never claimed as neural absence detection.
    """

    __tablename__ = "asset_passes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    observed: Mapped[bool] = mapped_column(default=False)
    source_type: Mapped[str] = mapped_column(String(32), default="PHONE")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoadSegment(Base):
    __tablename__ = "road_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    traffic_exposure: Mapped[float] = mapped_column(Float, default=100.0)
    pedestrian_exposure: Mapped[float] = mapped_column(Float, default=40.0)
    health_score: Mapped[float] = mapped_column(Float, default=80.0)
    active_defects: Mapped[int] = mapped_column(Integer, default=0)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
