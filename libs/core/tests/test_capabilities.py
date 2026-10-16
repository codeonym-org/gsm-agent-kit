import ast
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import assert_type

import gsm_agent_core
import pytest
from gsm_agent_core.capabilities.catalog import (
    DEVICE_STATUS_READ,
    CapabilityBinding,
    CapabilityKey,
    CapabilitySet,
)
from gsm_agent_core.capabilities.status import DeviceStatusReader
from gsm_agent_core.domain.devices import Availability, DeviceStatus


class OfflineStatus:
    async def read(self) -> DeviceStatus:
        return DeviceStatus(Availability.UNAVAILABLE, datetime.now(UTC))


async def test_supported_unavailable_port_is_typed_and_does_not_disappear() -> None:
    port = OfflineStatus()
    capabilities = CapabilitySet(CapabilityBinding(DEVICE_STATUS_READ, port))
    reader = capabilities.get(DEVICE_STATUS_READ)
    assert_type(reader, DeviceStatusReader | None)
    assert reader is not None
    assert reader is port
    assert (await reader.read()).availability is Availability.UNAVAILABLE
    assert capabilities.supported == (DEVICE_STATUS_READ.id,)


def test_lookup_requires_the_canonical_key_not_an_identical_name() -> None:
    capabilities = CapabilitySet(CapabilityBinding(DEVICE_STATUS_READ, OfflineStatus()))
    invented_key = CapabilityKey(DEVICE_STATUS_READ.id, DeviceStatusReader)
    assert capabilities.get(invented_key) is None
    assert CapabilitySet().get(DEVICE_STATUS_READ) is None
    with pytest.raises(ValueError, match="canonical capability key"):
        CapabilityBinding(invented_key, OfflineStatus())


def test_conflicting_bindings_fail_before_device_operations() -> None:
    binding = CapabilityBinding(DEVICE_STATUS_READ, OfflineStatus())
    with pytest.raises(ValueError, match="bound twice"):
        CapabilitySet(binding, binding)


def test_core_imports_only_standard_library_and_itself() -> None:
    assert gsm_agent_core.__file__ is not None
    root = Path(gsm_agent_core.__file__).parent
    for source in root.rglob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            assert set(names) <= sys.stdlib_module_names | {"gsm_agent_core"}
