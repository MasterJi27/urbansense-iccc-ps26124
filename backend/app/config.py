from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "UrbanSense"
    app_env: str = "development"
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 720
    field_token_expire_minutes: int = 45
    algorithm: str = "HS256"
    demo_api_enabled: bool = True

    database_url: str = "postgresql+psycopg://urbansense:urbansense@localhost:5432/urbansense"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    evidence_dir: str = "../storage/evidence"
    public_base_url: str = "http://localhost:8000"

    dpdp_retention_days: int = 30

    fusion_max_distance_meters: float = 40.0
    fusion_max_time_seconds: int = 21600
    fusion_compatible_only: bool = True
    clear_pass_expire_after: int = 3
    clear_pass_repair_after: int = 2

    health_defect_penalty: float = 8.0
    health_severity_high: float = 12.0
    health_recurrence_penalty: float = 5.0
    health_traffic_weight: float = 0.02
    health_pedestrian_weight: float = 0.03

    demo_seed_on_start: bool = True

    azure_vision_endpoint: str = ""
    azure_storage_account_url: str = ""
    azure_storage_container: str = "evidence"
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"  # deployment name; student SKU may host gpt-4.1-nano behind it
    azure_contentsafety_endpoint: str = ""
    applicationinsights_connection_string: str = ""
    still_max_bytes: int = 3_500_000
    allow_lan_camera_pull: bool = True
    azure_maps_subscription_key: str = Field(
        default="",
        validation_alias=AliasChoices("AZURE_MAPS_SUBSCRIPTION_KEY", "AZURE_MAPS_KEY"),
    )

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        pub = self.public_base_url.strip().rstrip("/")
        if pub and pub not in origins:
            origins.append(pub)
        return origins

    @property
    def is_development(self) -> bool:
        return self.app_env.strip().lower() in {"development", "test", "testing"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
