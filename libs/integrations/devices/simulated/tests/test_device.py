import pytest
from gsm_agent_core.capabilities.catalog import CAPABILITIES, DEVICE_STATUS_READ
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.ports import CellularDevice
from gsm_agent_simulated import SimulatedDevice


async def test_declared_support_matches_ports_and_stays_fixed_until_close() -> None:
    device: CellularDevice = SimulatedDevice(CellularDeviceId("contract-test"))
    descriptor = await device.describe()
    assert descriptor.device_id == device.device_id
    assert descriptor.adapter == device.manifest
    assert descriptor.adapter.capabilities == tuple(key.id for key in CAPABILITIES if device.get(key))
    reader = device.get(DEVICE_STATUS_READ)
    assert reader is not None
    await device.close()
    assert device.get(DEVICE_STATUS_READ) is reader
    with pytest.raises(RuntimeError, match="closed"):
        await reader.read()
