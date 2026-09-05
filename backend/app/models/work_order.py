from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utcnow, uuid_str


class WorkOrderStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    RE_VERIFICATION = "RE_VERIFICATION"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    public_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[WorkOrderStatus] = mapped_column(SAEnum(WorkOrderStatus), default=WorkOrderStatus.PENDING, index=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    qr_payload: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    repair_notes: Mapped[str] = mapped_column(Text, default="")
    repair_evidence_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verify_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    event = relationship("UrbanEvent", back_populates="work_orders")
    assignee = relationship("User", back_populates="work_orders")


class Repair(Base):
    __tablename__ = "repairs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    evidence_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result: Mapped[str] = mapped_column(String(32), default="SUBMITTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
