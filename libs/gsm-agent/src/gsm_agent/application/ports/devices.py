"""Application access to installed adapters and explicitly configured devices."""

from typing import Protocol

from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId
from gsm_agent_core.ports import CellularDevice


class DeviceDirectory(Protocol):
    def adapters(self) -> tuple[AdapterManifest, ...]: ...

    def devices(self) -> tuple[CellularDevice, ...]: ...

    def get(self, device_id: CellularDeviceId) -> CellularDevice: ...
