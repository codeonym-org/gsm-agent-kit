import json
import math
from typing import NoReturn, Self

import httpx

from gsm_agent_cli.runtime.settings import Settings

MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, message: str, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class OperatorApi:
    """One explicit GET per operation, with no redirect or retry policy."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Accept": "application/json"}
        if settings.api_token:
            headers["Authorization"] = f"Bearer {settings.api_token}"
        self._client = httpx.Client(
            base_url=settings.api_url,
            headers=headers,
            timeout=settings.timeout_seconds,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()

    def get(self, path: str, *, params: dict[str, int] | None = None, many: bool = False) -> object:
        try:
            with self._client.stream("GET", path, params=params) as response:
                self._check_status(response.status_code)
                if response.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                    raise ApiError("The backend returned an invalid JSON response.")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise ApiError(
                            "The backend response exceeded the 8 MiB limit; request a smaller page."
                        )
                try:
                    result = json.loads(
                        data, parse_constant=self._invalid_constant, parse_float=self._finite_float
                    )
                except (ValueError, UnicodeError, RecursionError):
                    raise ApiError("The backend returned an invalid JSON response.") from None
                if not isinstance(result, list if many else dict):
                    raise ApiError("The backend returned an unexpected JSON response shape.")
                return result
        except httpx.TimeoutException:
            raise ApiError("The backend request timed out; no retry was attempted.") from None
        except httpx.HTTPError:
            raise ApiError(
                "Cannot communicate with the backend; check its address and connectivity."
            ) from None

    @staticmethod
    def _invalid_constant(value: str) -> NoReturn:
        raise ValueError("Non-finite JSON number")

    @staticmethod
    def _finite_float(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Non-finite JSON number")
        return result

    @staticmethod
    def _check_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise ApiError("Backend access denied; check GSM_API_TOKEN.", 4)
        if status == 501:
            raise ApiError("The selected device does not support this capability.", 5)
        if status == 404:
            raise ApiError("The requested device or record was not found.", 6)
        if status == 409:
            raise ApiError("The device or operation is busy or conflicting; no retry was attempted.", 7)
        if 300 <= status < 400:
            raise ApiError("The backend returned a redirect; redirects are disabled.", 8)
        raise ApiError(f"Backend request failed (HTTP {status}); no retry was attempted.", 8)
