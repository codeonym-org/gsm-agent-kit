from collections.abc import Iterable

from gsm_agent.application.errors import DeviceNotFoundError
from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId
from gsm_agent_core.ports import CellularDevice


class ConfiguredDevices:
    """An explicit immutable selection; hardware probing never selects an adapter."""

    def __init__(self, devices: Iterable[CellularDevice], adapters: Iterable[AdapterManifest]) -> None:
        self._devices = tuple(devices)
        self._adapters = tuple(adapters)
        self._by_id = {device.device_id: device for device in self._devices}
        if len(self._by_id) != len(self._devices):
            raise ValueError("Duplicate logical cellular device ID")
        manifests = {adapter.adapter_id: adapter for adapter in self._adapters}
        if len(manifests) != len(self._adapters):
            raise ValueError("Duplicate adapter ID")
        for device in self._devices:
            if manifests.get(device.manifest.adapter_id) != device.manifest:
                raise ValueError("Device manifest must match an installed adapter")

    def adapters(self) -> tuple[AdapterManifest, ...]:
        return self._adapters

    def devices(self) -> tuple[CellularDevice, ...]:
        return self._devices

    def get(self, device_id: CellularDeviceId) -> CellularDevice:
        try:
            return self._by_id[device_id]
        except KeyError:
            raise DeviceNotFoundError(device_id) from None
