"""A development cellular device; never represents verified physical hardware."""

from datetime import UTC, datetime
from importlib.metadata import version

from gsm_agent_core.capabilities.catalog import (
    DEVICE_STATUS_READ,
    CapabilityBinding,
    CapabilityKey,
    CapabilitySet,
)
from gsm_agent_core.domain.devices import (
    AdapterManifest,
    Availability,
    CellularDeviceId,
    DeviceDescriptor,
    DeviceModel,
    DeviceStatus,
)

MANIFEST = AdapterManifest(
    adapter_id="simulated",
    version=version("gsm-agent-simulated"),
    model=DeviceModel("GSM Agent Kit", "Simulated cellular device"),
    capabilities=(DEVICE_STATUS_READ.id,),
)


class SimulatedDevice:
    def __init__(
        self, device_id: CellularDeviceId, *, availability: Availability = Availability.READY
    ) -> None:
        self._device_id = device_id
        self._availability = availability
        self._capabilities = CapabilitySet(CapabilityBinding(DEVICE_STATUS_READ, self))
        self.closed = False

    @property
    def device_id(self) -> CellularDeviceId:
        return self._device_id

    @property
    def manifest(self) -> AdapterManifest:
        return MANIFEST

    async def describe(self) -> DeviceDescriptor:
        return DeviceDescriptor(self.device_id, self.manifest)

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return self._capabilities.get(key)

    async def read(self) -> DeviceStatus:
        if self.closed:
            raise RuntimeError("Simulated device is closed")
        return DeviceStatus(self._availability, datetime.now(UTC))

    async def close(self) -> None:
        self.closed = True
