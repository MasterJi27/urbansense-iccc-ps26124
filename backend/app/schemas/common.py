from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.event import EventStatus, EventType, Severity, SourceType
from app.models.user import UserRole
from app.models.work_order import WorkOrderStatus


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: str
    full_name: str
    scope: str = "iccc"


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class FieldJoinIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class FieldBoothOut(BaseModel):
    code: str
    expires_in: int
    redeemed: bool = False
    join_path: str = "/field"
    note: str = "iPhone Safari opens /field, enters this PIN once, uses the phone camera. No Flutter install."


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str
    role: UserRole = UserRole.OPERATOR


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class MeOut(UserOut):
    scope: str = "iccc"


class ObservationIn(BaseModel):
    event_type: EventType
    severity: Severity = Severity.MEDIUM
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    gps_accuracy: float | None = None
    timestamp: datetime | None = None
    source_type: SourceType = SourceType.PHONE
    source_id: str = Field(min_length=1, max_length=80)
    sensor_id: str | None = None
    bus_id: str | None = None
    route_id: str | None = None
    confidence: float = Field(ge=0, le=1, default=0.5)
    simulated: bool = False
    heading: float | None = None
    speed_kmh: float | None = None
    plate_text: str | None = Field(default=None, max_length=32)
    plate_confidence: float | None = None
    evidence_url: str | None = None
    thumbnail_url: str | None = None
    extra: dict[str, Any] | None = None
    client_id: str | None = None


class ObservationOut(BaseModel):
    id: str
    event_type: EventType
    severity: Severity
    latitude: float
    longitude: float
    gps_accuracy: float | None
    timestamp: datetime
    source_type: SourceType
    source_id: str
    sensor_id: str | None
    bus_id: str | None
    confidence: float
    simulated: bool
    plate_text: str | None
    plate_confidence: float | None
    evidence_url: str | None
    extra: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: str
    public_code: str
    event_type: EventType
    severity: Severity
    status: EventStatus
    latitude: float
    longitude: float
    gps_accuracy: float | None
    timestamp: datetime
    source_id: str
    sensor_id: str | None
    bus_id: str | None
    route_id: str | None
    confidence: float
    evidence_url: str | None
    thumbnail_url: str | None
    extra: dict | None
    fusion_group_id: str
    verification_count: int
    source_count: int
    observation_count: int
    fusion_reason: str
    simulated: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EventPatch(BaseModel):
    status: EventStatus | None = None
    severity: Severity | None = None


class VerifyIn(BaseModel):
    notes: str = ""


class HeartbeatIn(BaseModel):
    sensor_id: str | None = None
    sensor_code: str | None = None
    bus_code: str | None = None
    camera_status: str = "ONLINE"
    gps_status: str = "ONLINE"
    imu_status: str = "ONLINE"
    battery_pct: float | None = None
    temperature_c: float | None = None
    storage_free_mb: float | None = None
    network_type: str = "UNKNOWN"
    ai_mode: str = "SIMULATION"
    processing_mode: str | None = None
    sync_state: str = "IDLE"
    latitude: float | None = None
    longitude: float | None = None
    heading: float | None = None
    speed_kmh: float | None = None


class SensorBindIn(BaseModel):
    sensor_code: str
    bus_code: str
    device_label: str = "PHONE"


class CameraIn(BaseModel):
    code: str = Field(min_length=3, max_length=64)
    vendor: str = "GENERIC"
    bay: str = "FRONT"
    bus_code: str | None = None
    kind: str = "BUS_CCTV"
    label: str = ""


class CameraPullIn(BaseModel):
    snapshot_url: str
    code: str = "CAM-DVR-01"
    vendor: str = "HTTP_SNAPSHOT"
    bay: str = "FRONT"
    bus_code: str | None = None
    kind: str = "BUS_CCTV"
    latitude: float = 28.6328
    longitude: float = 77.2195


class WorkOrderIn(BaseModel):
    event_id: str | None = None
    asset_id: str | None = None
    title: str
    description: str = ""
    assignee_id: str | None = None


class WorkOrderPatch(BaseModel):
    status: WorkOrderStatus | None = None
    assignee_id: str | None = None
    title: str | None = None


class RepairIn(BaseModel):
    notes: str = ""
    evidence_url: str | None = None


class VerifyRepairIn(BaseModel):
    passed: bool
    notes: str = ""


class AssetIn(BaseModel):
    code: str
    asset_type: str
    name: str
    latitude: float
    longitude: float
    condition: str = "UNKNOWN"


class AssetPassIn(BaseModel):
    latitude: float
    longitude: float
    observed: bool = False
    source_type: str = "PHONE"
    source_id: str = ""


class BusIn(BaseModel):
    code: str
    registration: str = ""
    route_id: str | None = None


class TripIn(BaseModel):
    bus_id: str | None = None
    sensor_id: str | None = None
    route_id: str | None = None
    simulated: bool = False


class BridgeBatchIn(BaseModel):
    # Phone accel batch while traversing a bridge geofence — matched to bridge via GPS
    latitude: float
    longitude: float
    gps_accuracy: float | None = None
    speed_kmh: float | None = None
    timestamp: datetime | None = None
    source_type: SourceType = SourceType.PHONE
    source_id: str
    sensor_id: str | None = None
    bus_id: str | None = None
    route_id: str | None = None
    simulated: bool = False
    # Raw accel magnitude after gravity removal is computed server-side; send samples
    samples: list[dict]  # each {t, ax, ay, az} t=unix sec
    bridge_code_hint: str | None = None
    extra: dict | None = None  # temp_c, joint_photo hint


class InspectIn(BaseModel):
    # Bridge inspection checklist — minimal, stored as JSON in Inspection.checklist
    joint_gap: Any | None = None
    bearing: Any | None = None
    crack: Any | None = None
    waterlogging: Any | None = None
    overall: Any | None = None
    notes: str | None = None
    condition: str | None = None
    checklist: dict[str, Any] | None = None


class CitizenReportIn(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=2000)
    severity: Severity = Severity.MEDIUM
    gps_accuracy: float | None = None
    contact: str | None = Field(default=None, max_length=64)
    asset_code: str | None = Field(default=None, max_length=64)
    qr_payload: str | None = Field(default=None, max_length=256)
    claim_token: str | None = Field(default=None, max_length=4000)
    extra: dict[str, Any] | None = None


class NotificationOut(BaseModel):
    id: str
    title: str
    message: str
    severity: str
    event_id: str | None
    work_order_id: str | None
    channel: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
