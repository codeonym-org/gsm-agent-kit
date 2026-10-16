import math
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class ZteMf833tSettings:
    base_url: str = "http://192.168.0.1"
    timeout_seconds: float = 3
    inbox_timeout_seconds: float = 10
    page_size: int = 50
    max_pages: int = 100
    storage_generation: str = "initial"
    subscription_generation: str = "initial"
    send_timeout_seconds: float = 30
    send_poll_interval_seconds: float = 1

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
        if not math.isfinite(self.inbox_timeout_seconds) or not 0 < self.inbox_timeout_seconds <= 120:
            raise ValueError("ZTE inbox timeout must be finite, positive and at most 120 seconds")
        if not 1 <= self.page_size <= 500 or not 1 <= self.max_pages <= 1000:
            raise ValueError("Invalid inbox pagination limits")
        if not math.isfinite(self.send_timeout_seconds) or not 0 < self.send_timeout_seconds <= 120:
            raise ValueError("Send timeout must be finite, positive and at most 120 seconds")
        if not math.isfinite(self.send_poll_interval_seconds) or not 0 < self.send_poll_interval_seconds <= 5:
            raise ValueError("Send poll interval must be finite, positive and at most 5 seconds")
        if any(
            not value.strip() or len(value) > 128
            for value in (self.storage_generation, self.subscription_generation)
        ):
            raise ValueError("Inbox generations must contain 1–128 characters")
