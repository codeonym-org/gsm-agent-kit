# gsm-agent-standard-tests

Reusable pytest contracts for the framework-independent `CellularDevice` interface.
The package depends on core, pytest and pytest-asyncio; it does not depend on the
application library, backend or any adapter. It is development tooling and is not
installed by the selected production server profile.

## Adopt the suite

Inherit `DeviceContractTests` in a pytest-collected `Test*` class. Supply a
**function-scoped** `cellular_device` fixture that yields a fresh device and closes
it in `finally`. The suite has explicit asyncio markers; it works with
pytest-asyncio's strict or auto mode. Use `pytest_asyncio.fixture` for async fixtures.

This complete example uses the synthetic adapter:

```python
from collections.abc import AsyncIterator

import pytest_asyncio
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_simulated import SimulatedDevice
from gsm_agent_standard_tests import DeviceContractTests


@pytest_asyncio.fixture
async def cellular_device() -> AsyncIterator[SimulatedDevice]:
    device = SimulatedDevice(CellularDeviceId("contract-device"))
    try:
        yield device
    finally:
        await device.close()


class TestMyDevice(DeviceContractTests):
    pass
```

For a new model, replace construction with its adapter and an explicit synthetic
transport. Keep its protocol assertions in the adapter's own tests. Parametrize
the fixture to exercise different selected capabilities and availability states.
No global pytest plugin or automatic device discovery is registered.

From the repository root:

```bash
uv sync --locked --all-packages --all-extras
uv run --no-sync pytest -q \
  libs/integrations/devices/simulated/tests/test_contract.py \
  libs/integrations/devices/zte-mf833t/tests/test_contract.py
```

## Checks and limits

The suite checks descriptor/logical identity, declared versus bound canonical
capabilities, port protocol shape, evidence scope, stable identity and support
across reads, and repeated cleanup. Noncanonical keys must not resolve. An adapter
claiming verified compatibility needs device-verification evidence matching its
observed variant and covering every declared capability; evidence for the same
variant may be combined. Fixture evidence alone is insufficient.

Supported status/inbox ports are explicitly read and must return domain
observations. An inbox source must belong to the opened logical device. A status
observation may be unavailable: temporary availability does not remove support.
Only undeclared read capabilities skip their read tests; a declared but missing
port fails. A successful inbox fixture may be empty or include incomplete messages.
Read errors propagate as failures, so supply a successful fixture for these checks;
offline inbox, malformed responses and cancellation belong in protocol tests.

SMS-send and balance interfaces are inspected through canonical lookup and
runtime protocol checks. The suite **never calls `submit`, `reserve` or `consult`**.
It does not validate sending, carrier ownership, read-only wire behavior, timeouts,
recovery, or physical-device compatibility. Runtime protocol checks establish the
presence of members, not their full signatures or behavior.

The fixture controls all access. A fixture that opens real hardware would perform
real reads when these tests are explicitly collected; there is no implicit opt-in
gate for a caller-supplied fixture. Keep normal CI fixtures synthetic. Hardware
verification requires a separate deliberate run, and private SMS/device details
must stay out of committed output and public artifacts. Passing this suite never
promotes an adapter's compatibility evidence to device verification.
