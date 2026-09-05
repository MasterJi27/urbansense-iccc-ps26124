from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user import utcnow, uuid_str


class BridgeHealthLog(Base):
    __tablename__ = "bridge_health_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    bridge_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), index=True)
    rms: Mapped[float] = mapped_column(Float)
    peak: Mapped[float] = mapped_column(Float)
    crest: Mapped[float] = mapped_column(Float)
    dominant_freq: Mapped[float] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), default="")
    health_score: Mapped[float] = mapped_column(Float)
    anomaly: Mapped[str] = mapped_column(String(16), default="NO")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str] = mapped_column(Text, default="")
