from pathlib import Path
from typing import Literal

from gsm_agent_core.domain.balance import BalanceCarrier
from gsm_agent_core.domain.devices import Availability
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ZteHttpSettings(BaseModel):
    base_url: str = "http://192.168.0.1"
    timeout_seconds: float = Field(default=3, gt=0, le=30, allow_inf_nan=False)
    inbox_timeout_seconds: float = Field(default=10, gt=0, le=120, allow_inf_nan=False)
    page_size: int = Field(default=50, ge=1, le=500)
    max_pages: int = Field(default=100, ge=1, le=1000)
    storage_generation: str = Field(default="initial", min_length=1, max_length=128, pattern=r"\S")
    subscription_generation: str = Field(default="initial", min_length=1, max_length=128, pattern=r"\S")
    send_timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    send_poll_interval_seconds: float = Field(default=1, gt=0, le=5, allow_inf_nan=False)


class BalanceSettings(BaseModel):
    carrier: BalanceCarrier | None = None
    timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    cleanup_timeout_seconds: float = Field(default=2, gt=0, le=5, allow_inf_nan=False)


class InboxSettings(BaseModel):
    enabled: bool = False
    database_path: Path = Path("data/inbox.sqlite3")
    poll_interval_seconds: float = Field(default=5, gt=0, le=3600, allow_inf_nan=False)
    timeout_seconds: float = Field(default=15, gt=0, le=120, allow_inf_nan=False)


class SubmissionSettings(BaseModel):
    enabled: bool = False
    database_path: Path = Path("data/submissions.sqlite3")
    timeout_seconds: float = Field(default=100, gt=0, le=600, allow_inf_nan=False)
    max_total_chars: int = Field(default=240, ge=16, le=10000)
    max_parts: int = Field(default=3, ge=1, le=9)


class DeviceSettings(BaseModel):
    id: str = Field(default="demo-device", pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    adapter: Literal["simulated", "zte-mf833t"] = "simulated"
    simulated_availability: Availability = Availability.READY
    simulated_balance_enabled: bool = False
    zte_mf833t: ZteHttpSettings = Field(default_factory=ZteHttpSettings)


class AssistantSettings(BaseModel):
    enabled: bool = False
    dry_run: bool = True
    database_path: Path = Path("data/conversations.sqlite3")
    model: str = Field(default="openai/gpt-4.1-mini", min_length=1)
    api_key: SecretStr | None = Field(default=None, min_length=1)
    instructions: str = "You are a helpful general SMS assistant. Reply in the sender's language."
    max_output_tokens: int = Field(default=384, ge=64, le=4096)
    timeout_seconds: float = Field(default=60, gt=0, le=300, allow_inf_nan=False)
    poll_interval_seconds: float = Field(default=2, gt=0, le=60, allow_inf_nan=False)
    default_region: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    history_max_messages: int = Field(default=20, ge=2, le=200)
    history_max_chars: int = Field(default=6000, ge=256, le=100000)
    history_retention_days: int = Field(default=30, ge=1, le=365)
    input_max_chars: int = Field(default=2000, ge=16, le=10000)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GSM_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    device: DeviceSettings = Field(default_factory=DeviceSettings)
    inbox: InboxSettings = Field(default_factory=InboxSettings)
    submissions: SubmissionSettings = Field(default_factory=SubmissionSettings)
    assistant: AssistantSettings = Field(default_factory=AssistantSettings)
    balance: BalanceSettings = Field(default_factory=BalanceSettings)
    query_timeout_seconds: float = Field(default=5, gt=0, le=30, allow_inf_nan=False)
    api_token: SecretStr | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def assistant_dependencies(self) -> "Settings":
        if self.assistant.enabled:
            if not self.inbox.enabled:
                raise ValueError("Auto-reply requires inbox ingestion")
            if not self.assistant.dry_run and not self.submissions.enabled:
                raise ValueError("Live auto-reply requires SMS submission")
        return self
