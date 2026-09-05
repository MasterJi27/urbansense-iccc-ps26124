from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utcnow, uuid_str


class EventType(str, Enum):
    POTHOLE = "POTHOLE"
    ROAD_DAMAGE = "ROAD_DAMAGE"
    WATERLOGGING = "WATERLOGGING"
    MISSING_DIVIDER = "MISSING_DIVIDER"
    MISSING_ZEBRA = "MISSING_ZEBRA"
    DAMAGED_SIGN = "DAMAGED_SIGN"
    ROAD_OBSTRUCTION = "ROAD_OBSTRUCTION"
    TRAFFIC_CONGESTION = "TRAFFIC_CONGESTION"
    PEDESTRIAN_RISK = "PEDESTRIAN_RISK"
    SCHOOL_CROSSING = "SCHOOL_CROSSING"
    HIT_AND_RUN = "HIT_AND_RUN"
    RASH_DRIVING = "RASH_DRIVING"
    VEHICLE = "VEHICLE"
    PEDESTRIAN = "PEDESTRIAN"
    # 26124.5 Bridge/Flyover SHM — phone accelerometer + bus GPS crowd
    BRIDGE_VIBRATION = "BRIDGE_VIBRATION"
    FLYOVER_JOINT = "FLYOVER_JOINT"
    BRIDGE_ANOMALY = "BRIDGE_ANOMALY"
    OTHER = "OTHER"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventStatus(str, Enum):
    NEW = "NEW"
    UNVERIFIED = "UNVERIFIED"
    CONFIRMED = "CONFIRMED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    REPAIRED = "REPAIRED"
    RE_VERIFICATION = "RE_VERIFICATION"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    REJECTED = "REJECTED"


class SourceType(str, Enum):
    PHONE = "PHONE"
    BUS_CCTV = "BUS_CCTV"
    ROAD_CCTV = "ROAD_CCTV"
    IOT = "IOT"
    INSPECTOR = "INSPECTOR"
    DEMO = "DEMO"


class Observation(Base):
    """A single sensor/human observation. Not the fused real-world event."""

    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType), index=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), default=Severity.MEDIUM)
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    gps_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source_type: Mapped[SourceType] = mapped_column(SAEnum(SourceType), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    sensor_id: Mapped[str | None] = mapped_column(ForeignKey("sensor_nodes.id"), nullable=True)
    bus_id: Mapped[str | None] = mapped_column(ForeignKey("buses.id"), nullable=True)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    plate_text: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plate_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event_links = relationship("EventObservation", back_populates="observation")


class UrbanEvent(Base):
    """Fused real-world occurrence clustered from observations."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    public_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType), index=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), default=Severity.MEDIUM, index=True)
    status: Mapped[EventStatus] = mapped_column(SAEnum(EventStatus), default=EventStatus.UNVERIFIED, index=True)
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float, index=True)
    gps_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source_id: Mapped[str] = mapped_column(String(64), default="")
    sensor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    bus_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fusion_group_id: Mapped[str] = mapped_column(String(36), index=True, default=uuid_str)
    verification_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    observation_count: Mapped[int] = mapped_column(Integer, default=1)
    fusion_reason: Mapped[str] = mapped_column(Text, default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    road_segment_id: Mapped[str | None] = mapped_column(ForeignKey("road_segments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    observation_links = relationship("EventObservation", back_populates="event")
    work_orders = relationship("WorkOrder", back_populates="event")


class EventObservation(Base):
    __tablename__ = "event_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), index=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.id"), index=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event = relationship("UrbanEvent", back_populates="observation_links")
    observation = relationship("Observation", back_populates="event_links")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    observation_id: Mapped[str | None] = mapped_column(ForeignKey("observations.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="image")
    url: Mapped[str] = mapped_column(String(512))
    restricted: Mapped[bool] = mapped_column(Boolean, default=True)
    blur_faces: Mapped[bool] = mapped_column(Boolean, default=True)
    blur_plates: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
