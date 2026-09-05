from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.user import utcnow, uuid_str


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    sensor_id: Mapped[str | None] = mapped_column(ForeignKey("sensor_nodes.id"), nullable=True)
    client_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OK")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def is_retention_expired(self) -> bool:
        return is_retention_expired(self.created_at)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def is_retention_expired(self) -> bool:
        return is_retention_expired(self.created_at)


class NotificationLog(Base):
    """Simple in-app notification log for bridge CRITICAL auto-WO and citizen QR reports."""

    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="INFO", index=True)
    event_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    work_order_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(32), default="in_app")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# DPDP retention (30 days) — placeholder expiry logic for audit/sync logs
def retention_expiry_date(created_at: datetime, retention_days: int | None = None) -> datetime:
    if retention_days is None:
        try:
            from app.config import get_settings

            retention_days = get_settings().dpdp_retention_days
        except Exception:
            retention_days = 30
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at + timedelta(days=retention_days)


def is_retention_expired(created_at: datetime, retention_days: int | None = None) -> bool:
    expiry = retention_expiry_date(created_at, retention_days)
    now = datetime.now(timezone.utc)
    return now >= expiry
