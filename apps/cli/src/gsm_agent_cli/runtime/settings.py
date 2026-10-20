import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """A configuration error whose message contains no setting values."""


@dataclass(frozen=True)
class Settings:
    api_url: str
    timeout_seconds: float
    api_token: str | None = field(default=None, repr=False)

    @classmethod
    def load(
        cls,
        env_file: Path | None = None,
        api_url: str | None = None,
        timeout_seconds: str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> "Settings":
        path = env_file if env_file is not None else Path.cwd() / ".env"
        try:
            if env_file is not None and not path.is_file():
                raise ConfigurationError("The selected env file is not a readable file.")
            # Interpolation is deliberately disabled: tokens remain literal and no
            # unrelated environment secrets can be substituted into the API URL.
            values = dotenv_values(path, interpolate=False) if path.is_file() else {}
        except (OSError, UnicodeError):
            raise ConfigurationError("Cannot read the env file.") from None
        process = os.environ if environ is None else environ

        def setting(key: str, default: str = "") -> str:
            return process.get(key, values.get(key) or default)

        url_value = api_url if api_url is not None else setting("GSM_CLI__API_URL", "http://127.0.0.1:8000")
        try:
            url = httpx.URL(url_value)
        except (httpx.InvalidURL, ValueError, UnicodeError):
            raise ConfigurationError(
                "API URL must be an HTTP(S) origin without credentials or a path."
            ) from None
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.path != "/"
            or url.query
            or url.fragment
            or url_value != url_value.strip()
            or "?" in url_value
            or "#" in url_value
            or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in url_value)
        ):
            raise ConfigurationError("API URL must be an HTTP(S) origin without credentials or a path.")
        try:
            timeout = float(
                timeout_seconds if timeout_seconds is not None else setting("GSM_CLI__TIMEOUT_SECONDS", "35")
            )
        except ValueError:
            raise ConfigurationError("Timeout must be a finite number between 1 and 120 seconds.") from None
        if not math.isfinite(timeout) or not 1 <= timeout <= 120:
            raise ConfigurationError("Timeout must be a finite number between 1 and 120 seconds.")
        token = setting("GSM_API_TOKEN") or None
        if token is not None and any(not 0x21 <= ord(char) <= 0x7E for char in token):
            raise ConfigurationError("GSM_API_TOKEN must contain visible ASCII characters without spaces.")
        return cls(str(url).rstrip("/"), timeout, token)
