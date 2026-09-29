from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_access_token: str = "change-me"
    ugc_renderer_mode: str = "mock"
    runpod_api_key: str = ""
    runpod_pod_id: str = ""
    runpod_session_name: str = ""
    max_session_hours: float = 6.0
    hf_token: str = ""
    session_hourly_rate_usd: float = 0.0
    session_started_at: str = ""
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
