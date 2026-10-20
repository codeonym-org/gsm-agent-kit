from typing import Protocol

from gsm_agent.application.runtime import RuntimeStatus


class RuntimeStatusReader(Protocol):
    async def read(self) -> RuntimeStatus:
        """Read recorded local observations without probing devices or providers."""
        ...
