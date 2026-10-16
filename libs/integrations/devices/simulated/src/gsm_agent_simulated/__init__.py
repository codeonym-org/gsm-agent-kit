"""A development cellular device; never represents verified physical hardware."""

from dataclasses import replace
from datetime import UTC, datetime
from importlib.metadata import version

from gsm_agent_core.capabilities.balance import BalanceSession
from gsm_agent_core.capabilities.catalog import (
    CARRIER_BALANCE_READ,
    DEVICE_STATUS_READ,
    CapabilityBinding,
    CapabilityKey,
    CapabilitySet,
)
from gsm_agent_core.domain.balance import BalanceIssue, BalanceReadError
from gsm_agent_core.domain.devices import (
    AdapterManifest,
    Availability,
    CellularDeviceId,
    DeviceDescriptor,
    DeviceModel,
    DeviceStatus,
)

from gsm_agent_simulated.balance import SimulatedBalanceReader

MANIFEST = AdapterManifest(
    adapter_id="simulated",
    version=version("gsm-agent-simulated"),
    model=DeviceModel("GSM Agent Kit", "Simulated cellular device"),
    capabilities=(DEVICE_STATUS_READ.id,),
)


class SimulatedDevice:
    def __init__(
        self,
        device_id: CellularDeviceId,
        *,
        availability: Availability = Availability.READY,
        balance_enabled: bool = False,
    ) -> None:
        self._device_id = device_id
        self._availability = availability
        self._balance = SimulatedBalanceReader() if balance_enabled else None
        self._capabilities = CapabilitySet(
            CapabilityBinding(DEVICE_STATUS_READ, self),
            *((CapabilityBinding(CARRIER_BALANCE_READ, self),) if balance_enabled else ()),
        )
        self._manifest = replace(MANIFEST, capabilities=self._capabilities.supported)
        self.closed = False

    @property
    def device_id(self) -> CellularDeviceId:
        return self._device_id

    @property
    def manifest(self) -> AdapterManifest:
        return self._manifest

    async def reserve(self) -> BalanceSession:
        if self.closed or self._availability is not Availability.READY or self._balance is None:
            raise BalanceReadError(BalanceIssue.UNAVAILABLE)
        return await self._balance.reserve()

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
