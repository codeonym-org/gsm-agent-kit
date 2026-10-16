from typing import Literal

from gsm_agent_core.domain.devices import Availability
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ZteHttpSettings(BaseModel):
    base_url: str = "http://192.168.0.1"
    timeout_seconds: float = Field(default=3, gt=0, le=30, allow_inf_nan=False)


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
    query_timeout_seconds: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)
    api_token: SecretStr | None = Field(default=None, min_length=1)
