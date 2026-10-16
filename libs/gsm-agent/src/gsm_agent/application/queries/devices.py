"""Read-only device operations, dispatched exclusively through QuerySender."""

import asyncio
import math
from dataclasses import dataclass

from gsm_agent_core.capabilities.catalog import DEVICE_STATUS_READ
from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId, DeviceDescriptor, DeviceStatus
from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.errors import DeviceQueryTimeoutError, UnsupportedCapabilityError
from gsm_agent.application.ports.devices import DeviceDirectory


@dataclass(frozen=True, slots=True)
class DeviceQueryPolicy:
    timeout_seconds: float = 5

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Query timeout must be finite and positive")


@query
@dataclass(frozen=True)
class ListAdapters(Query[tuple[AdapterManifest, ...]]):
    pass


@query_handler
class ListAdaptersHandler:
    def __init__(self, devices: DeviceDirectory) -> None:
        self.devices = devices

    async def handle(self, request: ListAdapters) -> tuple[AdapterManifest, ...]:
        return self.devices.adapters()


@query
@dataclass(frozen=True)
class ListDevices(Query[tuple[DeviceDescriptor, ...]]):
    pass


@query_handler
class ListDevicesHandler:
    def __init__(self, devices: DeviceDirectory, policy: DeviceQueryPolicy) -> None:
        self.devices = devices
        self.policy = policy

    async def handle(self, request: ListDevices) -> tuple[DeviceDescriptor, ...]:
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                return tuple([await device.describe() for device in self.devices.devices()])
        except TimeoutError as exc:
            raise DeviceQueryTimeoutError("Device description exceeded its deadline") from exc


@query
@dataclass(frozen=True)
class GetDevice(Query[DeviceDescriptor]):
    device_id: CellularDeviceId


@query_handler
class GetDeviceHandler:
    def __init__(self, devices: DeviceDirectory, policy: DeviceQueryPolicy) -> None:
        self.devices = devices
        self.policy = policy

    async def handle(self, request: GetDevice) -> DeviceDescriptor:
        device = self.devices.get(request.device_id)
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                return await device.describe()
        except TimeoutError as exc:
            raise DeviceQueryTimeoutError("Device description exceeded its deadline") from exc


@query
@dataclass(frozen=True)
class GetDeviceStatus(Query[DeviceStatus]):
    device_id: CellularDeviceId


@query_handler
class GetDeviceStatusHandler:
    def __init__(self, devices: DeviceDirectory, policy: DeviceQueryPolicy) -> None:
        self.devices = devices
        self.policy = policy

    async def handle(self, request: GetDeviceStatus) -> DeviceStatus:
        reader = self.devices.get(request.device_id).get(DEVICE_STATUS_READ)
        if reader is None:
            raise UnsupportedCapabilityError(DEVICE_STATUS_READ.id)
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                return await reader.read()
        except TimeoutError as exc:
            raise DeviceQueryTimeoutError("Device status exceeded its deadline") from exc
