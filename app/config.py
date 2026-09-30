from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_access_token: str = "change-me"
    ugc_renderer_mode: str = "mock"
    session_model: str = "legacy"
    runpod_api_key: str = ""
    runpod_pod_id: str = ""
    runpod_gpu_count: int = Field(default=1, ge=1)
    runpod_session_name: str = ""
    max_session_hours: float = 6.0
    external_guardian: bool = False
    idle_timeout_seconds: int = Field(default=600, ge=60)
    render_timeout_seconds: int = Field(default=3600, ge=1)
    h3_enabled: bool = False
    h3_license_authorized: bool = False
    h3_allowed_region: str = ""
    h3_operator_region: str = ""
    h3_license_mode: str = "disabled"
    h3_authorization_reference: str = ""
    h3_sglang_url: str = "http://127.0.0.1:30010"
    h3_profile: str = "h100-4"
    h3_network_volume_id: str = ""
    h3_data_center_id: str = ""
    h3_worker_image: str = ""
    h3_model_ready_file: Path = Path("/tmp/ugc-h3-ready.json")
    hf_token: str = ""
    session_hourly_rate_usd: float = 0.0
    session_started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data_dir: Path = Path("/tmp/ugc-factory-data")
    max_upload_mb: int = 30
    ltx_runner_cmd: str = "bash scripts/run_ltx.sh"
    wan_runner_cmd: str = "bash scripts/run_wan.sh"
    skyreels_runner_cmd: str = "bash scripts/run_skyreels.sh"

    @property
    def session_started(self) -> datetime:
        if self.session_started_at:
            try:
                dt = datetime.fromisoformat(self.session_started_at.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)


settings = Settings()
