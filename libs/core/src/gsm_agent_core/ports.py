"""Device-facing ports; adapters expose only the capabilities they implement."""

from typing import Protocol

from gsm_agent_core.capabilities.catalog import CapabilityKey
from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId, DeviceDescriptor


class CellularDevice(Protocol):
    @property
    def device_id(self) -> CellularDeviceId: ...

    @property
    def manifest(self) -> AdapterManifest: ...

    async def describe(self) -> DeviceDescriptor: ...

    def get[P](self, key: CapabilityKey[P]) -> P | None: ...

    async def close(self) -> None: ...
