from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "SadakSaarthi"
    app_env: str = "development"
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 720
    field_token_expire_minutes: int = 45
    algorithm: str = "HS256"
    demo_api_enabled: bool = True
    # How many reverse proxies in front of the app append to X-Forwarded-For (Azure App Service = 1).
    # Unset: 1 outside development (App Service front end), 0 in development/test where uvicorn is hit directly.
    # 0 means X-Forwarded-For is ignored and the socket peer is the client.
    trusted_proxy_hops: int | None = Field(default=None, ge=0)

    database_url: str = "postgresql+psycopg://urbansense:urbansense@localhost:5432/urbansense"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    evidence_dir: str = "../storage/evidence"
    public_base_url: str = "http://localhost:8000"
    officer_sms_webhook: str = ""
    demo_corridor_lat: float = 28.6328
    demo_corridor_lon: float = 77.2195
    demo_corridor_radius_m: float = 0

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
    # Optional: tiles from any raster provider. A URL template with {z} {x} {y} (and optionally {s} {r}); put the provider
    # key inside the URL itself. The server fetches the tiles, so the key never reaches the browser. It wins over the
    # Azure Maps key. Unset: OpenStreetMap, drawn by the browser. Only the tiles change, not the place names.
    map_tile_url: str = ""
    map_tile_provider: str = ""  # label shown in the UI; defaults to the URL's host name
    map_tile_attribution: str = ""  # shown on the map: plain text, or <a href="https://..."> links
    composio_api_key: str = ""
    composio_notify_to: str = ""
    composio_notify_channel: str = "gmail"
    composio_entity_id: str = "default"
    composio_connected_account_id: str = ""

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

    @property
    def effective_trusted_proxy_hops(self) -> int:
        if self.trusted_proxy_hops is not None:
            return self.trusted_proxy_hops
        return 0 if self.is_development else 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
