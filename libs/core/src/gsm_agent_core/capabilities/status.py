"""A status observation never implies support for SMS, voice or USSD."""

from typing import Protocol, runtime_checkable

from gsm_agent_core.domain.devices import DeviceStatus


@runtime_checkable
class DeviceStatusReader(Protocol):
    async def read(self) -> DeviceStatus: ...
