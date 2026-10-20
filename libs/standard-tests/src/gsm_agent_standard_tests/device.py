"""Shared checks at the device interface; never submit SMS or consult a carrier."""

import pytest
from gsm_agent_core.capabilities.catalog import (
    CAPABILITIES,
    DEVICE_STATUS_READ,
    SMS_INBOX_READ,
    CapabilityKey,
)
from gsm_agent_core.domain.devices import (
    AdapterManifest,
    CellularDeviceId,
    Compatibility,
    DeviceDescriptor,
    DeviceStatus,
    VerificationKind,
)
from gsm_agent_core.domain.sms import InboxSnapshot
from gsm_agent_core.ports import CellularDevice


def _identity(device: CellularDevice) -> tuple[CellularDeviceId, AdapterManifest, tuple[bool, ...]]:
    return device.device_id, device.manifest, tuple(device.get(key) is not None for key in CAPABILITIES)


@pytest.mark.asyncio
class DeviceContractTests:
    """Inherit in a Test* class and supply a function-scoped cellular_device fixture.

    The fixture yields a fresh, opened device and closes it in a finally block.
    Status/inbox fixtures must permit successful reads, including non-ready status
    observations. Use separate adapter tests for read failures and cancellation.
    """

    async def test_descriptor_matches_open_device(self, cellular_device: CellularDevice) -> None:
        descriptor = await cellular_device.describe()
        assert isinstance(descriptor, DeviceDescriptor), "describe() must return DeviceDescriptor"
        assert descriptor.device_id == cellular_device.device_id, "Descriptor changed logical device identity"
        assert descriptor.adapter == cellular_device.manifest, (
            "Descriptor and opened-device manifest disagree"
        )

    @pytest.mark.parametrize("key", CAPABILITIES, ids=lambda key: key.id)
    async def test_declared_capability_has_matching_port(
        self, cellular_device: CellularDevice, key: CapabilityKey[object]
    ) -> None:
        port = cellular_device.get(key)
        if key.id in cellular_device.manifest.capabilities:
            assert port is not None, f"Declared capability {key.id} has no port"
            assert isinstance(port, key.port_type), f"Capability {key.id} has the wrong port interface"
        else:
            assert port is None, f"Undeclared capability {key.id} has a port"

    @pytest.mark.parametrize("key", CAPABILITIES, ids=lambda key: key.id)
    async def test_lookup_requires_canonical_key(
        self, cellular_device: CellularDevice, key: CapabilityKey[object]
    ) -> None:
        invented = CapabilityKey(key.id, key.port_type)
        assert cellular_device.get(invented) is None, "Lookup accepted a noncanonical capability key"

    async def test_manifest_uses_catalog_and_scoped_evidence(self, cellular_device: CellularDevice) -> None:
        manifest = cellular_device.manifest
        declared = set(manifest.capabilities)
        assert declared <= {key.id for key in CAPABILITIES}, "Manifest declares an unknown capability"
        for evidence in manifest.compatibility_evidence:
            assert evidence.reference.strip(), "Compatibility evidence needs a reference"
            assert set(evidence.capabilities) <= declared, "Evidence refers to an undeclared capability"

    async def test_verified_compatibility_has_device_evidence(self, cellular_device: CellularDevice) -> None:
        descriptor = await cellular_device.describe()
        observation = descriptor.observation
        if observation is None or observation.compatibility is not Compatibility.VERIFIED:
            return
        assert observation.variant is not None, "Verified compatibility needs an observed variant"
        matching = [
            evidence
            for evidence in descriptor.adapter.compatibility_evidence
            if evidence.kind is VerificationKind.DEVICE_VERIFICATION
            and evidence.variant == observation.variant
        ]
        assert matching, "Verified compatibility needs device evidence for the observed variant"
        verified = {capability for evidence in matching for capability in evidence.capabilities}
        assert set(descriptor.adapter.capabilities) <= verified, (
            "Verified compatibility needs device evidence for every declared capability"
        )

    async def test_description_preserves_identity_and_support(self, cellular_device: CellularDevice) -> None:
        before = _identity(cellular_device)
        await cellular_device.describe()
        await cellular_device.describe()
        assert _identity(cellular_device) == before, (
            "Description changed device identity, manifest or support"
        )

    async def test_status_read_preserves_identity_and_support(self, cellular_device: CellularDevice) -> None:
        if DEVICE_STATUS_READ.id not in cellular_device.manifest.capabilities:
            pytest.skip("Adapter does not declare device.status.read")
        reader = cellular_device.get(DEVICE_STATUS_READ)
        assert reader is not None, "Declared status capability has no port"
        before = _identity(cellular_device)
        status = await reader.read()
        assert isinstance(status, DeviceStatus), "Status reader must return DeviceStatus"
        assert _identity(cellular_device) == before, (
            "Status read changed device identity, manifest or support"
        )

    async def test_inbox_scan_belongs_to_device(self, cellular_device: CellularDevice) -> None:
        if SMS_INBOX_READ.id not in cellular_device.manifest.capabilities:
            pytest.skip("Adapter does not declare sms.inbox.read")
        inbox = cellular_device.get(SMS_INBOX_READ)
        assert inbox is not None, "Declared inbox capability has no port"
        before = _identity(cellular_device)
        snapshot = await inbox.scan()
        assert isinstance(snapshot, InboxSnapshot), "Inbox reader must return InboxSnapshot"
        assert snapshot.source.device_id == cellular_device.device_id, (
            "Inbox source belongs to another device"
        )
        assert _identity(cellular_device) == before, "Inbox scan changed device identity, manifest or support"

    async def test_close_is_repeatable_and_preserves_support(self, cellular_device: CellularDevice) -> None:
        before = _identity(cellular_device)
        await cellular_device.close()
        await cellular_device.close()
        assert _identity(cellular_device) == before, "Closing changed device identity, manifest or support"
