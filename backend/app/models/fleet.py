from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utcnow, uuid_str


class ProcessingMode(str, Enum):
    EDGE_AI = "EDGE_AI"
    LIGHTWEIGHT_EDGE_AI = "LIGHTWEIGHT_EDGE_AI"
    CAPTURE_AND_SENSOR = "CAPTURE_AND_SENSOR"
    CLOUD_ASSISTED = "CLOUD_ASSISTED"
    EDGE_GATEWAY = "EDGE_GATEWAY"


class Bus(Base):
    __tablename__ = "buses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    registration: Mapped[str] = mapped_column(String(32), default="")
    route_id: Mapped[str | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    qr_payload: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    route = relationship("Route")
    sensor_nodes = relationship("SensorNode", back_populates="bus")


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    planned_duration_minutes: Mapped[float] = mapped_column(Float, default=45.0)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    polyline: Mapped[str] = mapped_column(Text, default="")  # encoded lat,lon;lat,lon
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SensorNode(Base):
    __tablename__ = "sensor_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    bus_id: Mapped[str | None] = mapped_column(ForeignKey("buses.id"), nullable=True)
    device_label: Mapped[str] = mapped_column(String(128), default="PHONE")
    source_type: Mapped[str] = mapped_column(String(32), default="PHONE")
    processing_mode: Mapped[ProcessingMode] = mapped_column(
        SAEnum(ProcessingMode), default=ProcessingMode.CAPTURE_AND_SENSOR
    )
    camera_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    gps_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    imu_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_free_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    ai_mode: Mapped[str] = mapped_column(String(64), default="SIMULATION")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_state: Mapped[str] = mapped_column(String(32), default="IDLE")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bus = relationship("Bus", back_populates="sensor_nodes")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    bus_id: Mapped[str | None] = mapped_column(ForeignKey("buses.id"), nullable=True)
    sensor_id: Mapped[str | None] = mapped_column(ForeignKey("sensor_nodes.id"), nullable=True)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("routes.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
