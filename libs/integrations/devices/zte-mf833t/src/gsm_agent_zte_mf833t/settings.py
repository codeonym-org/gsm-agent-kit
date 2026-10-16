import math
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class ZteMf833tSettings:
    base_url: str = "http://192.168.0.1"
    timeout_seconds: float = 3

    def __post_init__(self) -> None:
        url = urlsplit(self.base_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise ValueError("ZTE base URL must be an HTTP(S) origin without credentials or a path")
        try:
            url.port
        except ValueError as exc:
            raise ValueError("Invalid ZTE base URL port") from exc
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 30:
            raise ValueError("ZTE timeout must be finite, positive and at most 30 seconds")
