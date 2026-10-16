from pathlib import Path
from typing import Literal

from gsm_agent_core.domain.devices import Availability
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ZteHttpSettings(BaseModel):
    base_url: str = "http://192.168.0.1"
    timeout_seconds: float = Field(default=3, gt=0, le=30, allow_inf_nan=False)
    inbox_timeout_seconds: float = Field(default=10, gt=0, le=120, allow_inf_nan=False)
    page_size: int = Field(default=50, ge=1, le=500)
    max_pages: int = Field(default=100, ge=1, le=1000)
    storage_generation: str = Field(default="initial", min_length=1, max_length=128, pattern=r"\S")
    subscription_generation: str = Field(default="initial", min_length=1, max_length=128, pattern=r"\S")


class InboxSettings(BaseModel):
    enabled: bool = False
    database_path: Path = Path("data/inbox.sqlite3")
    poll_interval_seconds: float = Field(default=5, gt=0, le=3600, allow_inf_nan=False)
    timeout_seconds: float = Field(default=15, gt=0, le=120, allow_inf_nan=False)


class DeviceSettings(BaseModel):
    id: str = Field(default="demo-device", pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    adapter: Literal["simulated", "zte-mf833t"] = "simulated"
    simulated_availability: Availability = Availability.READY
    zte_mf833t: ZteHttpSettings = Field(default_factory=ZteHttpSettings)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GSM_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    device: DeviceSettings = Field(default_factory=DeviceSettings)
    inbox: InboxSettings = Field(default_factory=InboxSettings)
    query_timeout_seconds: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)
    api_token: SecretStr | None = Field(default=None, min_length=1)
