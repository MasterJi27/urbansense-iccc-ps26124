from fastapi import APIRouter, Depends

from app.config import get_settings
from app.deps import require_roles
from app.models.user import User, UserRole
from app.services.model_metrics import load_model_metrics

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_public_settings(_: User = Depends(require_roles(UserRole.ADMIN))):
    s = get_settings()
    return {
        "fusion_max_distance_meters": s.fusion_max_distance_meters,
        "fusion_max_time_seconds": s.fusion_max_time_seconds,
        "clear_pass_expire_after": s.clear_pass_expire_after,
        "clear_pass_repair_after": s.clear_pass_repair_after,
        "health_defect_penalty": s.health_defect_penalty,
        "health_severity_high": s.health_severity_high,
        "health_recurrence_penalty": s.health_recurrence_penalty,
        "app_env": s.app_env,
        "allow_lan_camera_pull": s.allow_lan_camera_pull,
        "azure_maps_enabled": bool(s.azure_maps_subscription_key.strip()),
        "demo_api_enabled": s.demo_api_enabled,
        "docs_enabled": s.is_development,
        "rdd_eval": load_model_metrics(),
        "privacy": {
            "prefer_event_clips": True,
            "role_based_evidence": True,
            "face_blur_planned": True,
            "plate_blur_planned": True,
            "audit_logs": True,
            "plates_server_masked": True,
            "citizen_contact_masked": True,
        },
    }
