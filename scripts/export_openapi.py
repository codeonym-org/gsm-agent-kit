"""Write transport contracts without starting devices or reading local settings."""

import json
import sys
from pathlib import Path

from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import Settings
from pydantic_settings import SettingsConfigDict


class SchemaSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="GSM_SCHEMA_EXPORT_")


if __name__ == "__main__":
    schema = json.dumps(create_app(SchemaSettings()).openapi(), indent=2) + "\n"
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(schema, encoding="utf-8")
    else:
        print(schema, end="")
