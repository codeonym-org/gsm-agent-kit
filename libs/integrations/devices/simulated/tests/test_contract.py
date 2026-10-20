from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from gsm_agent_core.domain.devices import Availability, CellularDeviceId
from gsm_agent_simulated import SimulatedDevice
from gsm_agent_standard_tests import DeviceContractTests


@pytest_asyncio.fixture(params=["ready", "unavailable", "balance"])
async def cellular_device(request: pytest.FixtureRequest) -> AsyncIterator[SimulatedDevice]:
    device = SimulatedDevice(
        CellularDeviceId("contract-simulated"),
        availability=Availability.UNAVAILABLE if request.param == "unavailable" else Availability.READY,
        balance_enabled=request.param == "balance",
    )
    try:
        yield device
    finally:
        await device.close()


class TestSimulatedDeviceContract(DeviceContractTests):
    pass
