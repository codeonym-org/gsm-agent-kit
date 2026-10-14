from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from gsm_agent.runtime.config import AgentConfig, ListenerConfig, ModemConfig, StorageConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GSM_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    modem: ModemConfig = Field(default_factory=ModemConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    listener: ListenerConfig = Field(default_factory=ListenerConfig)
    api_token: SecretStr | None = None
    log_level: str = "INFO"
    trace_console: bool = False
