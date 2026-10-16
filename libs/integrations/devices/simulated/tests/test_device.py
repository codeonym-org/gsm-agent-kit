import pytest
from gsm_agent_core.capabilities.catalog import CAPABILITIES, CARRIER_BALANCE_READ, DEVICE_STATUS_READ
from gsm_agent_core.domain.balance import BalanceCarrier, BalanceIssue, BalanceReadError
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


async def test_simulated_balance_reservations_exclude_other_owners_and_closed_handles_are_harmless():
    device = SimulatedDevice(CellularDeviceId("synthetic"), balance_enabled=True)
    reader = device.get(CARRIER_BALANCE_READ)
    assert reader is not None
    assert set(device.manifest.capabilities) == {key.id for key in CAPABILITIES if device.get(key)}
    session = await reader.reserve()
    with pytest.raises(BalanceReadError) as busy:
        await reader.reserve()
    assert busy.value.issue is BalanceIssue.BUSY
    observation = await session.consult(BalanceCarrier.SIMULATED)
    assert "SIMULATED" in observation.raw_text
    assert observation.credit is None and observation.sms_allowance is None
    with pytest.raises(BalanceReadError):
        await session.consult(BalanceCarrier.SIMULATED)
    await session.close()
    other = await reader.reserve()
    await session.close()  # An old handle must never release the new owner's reservation.
    with pytest.raises(BalanceReadError) as still_busy:
        await reader.reserve()
    assert still_busy.value.issue is BalanceIssue.BUSY
    await other.close()
    await device.close()
    assert device.get(CARRIER_BALANCE_READ) is reader
    with pytest.raises(BalanceReadError) as offline:
        await reader.reserve()
    assert offline.value.issue is BalanceIssue.UNAVAILABLE
