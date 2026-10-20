"""Inject broken devices to demonstrate what the exported contract suite catches."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest
from gsm_agent_core.capabilities.catalog import (
    CAPABILITIES,
    CARRIER_BALANCE_READ,
    DEVICE_STATUS_READ,
    SMS_INBOX_READ,
    SMS_SEND,
    CapabilityKey,
)
from gsm_agent_core.domain.devices import (
    AdapterManifest,
    Availability,
    CapabilityId,
    CellularDeviceId,
    Compatibility,
    CompatibilityEvidence,
    DeviceDescriptor,
    DeviceModel,
    DeviceObservation,
    DeviceStatus,
    DeviceVariant,
    VerificationKind,
)
from gsm_agent_core.domain.sms import InboxSnapshot, InboxSource
from gsm_agent_core.domain.submission import SmsSendConstraints
from gsm_agent_standard_tests import DeviceContractTests


class DeviceDouble:
    """All four ports; any write or carrier reservation fails the test immediately."""

    def __init__(self) -> None:
        self.device_id = CellularDeviceId("synthetic")
        self.manifest = AdapterManifest(
            "synthetic", "0.1.0", DeviceModel("Fixture", "Fixture"), tuple(key.id for key in CAPABILITIES)
        )
        self.ports: dict[CapabilityKey[object], object] = dict.fromkeys(CAPABILITIES, self)
        self.descriptor: DeviceDescriptor | None = None
        self.snapshot_device_id = self.device_id
        self.mutate_on = ""
        self.closed_count = 0
        self.constraints = SmsSendConstraints()

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return cast(P | None, self.ports.get(key))

    async def describe(self) -> DeviceDescriptor:
        descriptor = self.descriptor or DeviceDescriptor(self.device_id, self.manifest)
        if self.mutate_on == "describe":
            self.ports.pop(DEVICE_STATUS_READ, None)
        return descriptor

    async def read(self) -> DeviceStatus:
        if self.mutate_on == "read":
            self.device_id = CellularDeviceId("changed")
        return DeviceStatus(Availability.UNAVAILABLE, datetime.now(UTC))

    async def scan(self) -> InboxSnapshot:
        if self.mutate_on == "scan":
            self.manifest = replace(self.manifest, version="changed")
        now = datetime.now(UTC)
        return InboxSnapshot(
            InboxSource(self.snapshot_device_id, "initial", "fixture"), "initial", now, now, ()
        )

    async def submit(self, sms):
        raise AssertionError("The shared suite must never submit SMS")

    async def reserve(self):
        raise AssertionError("The shared suite must never reserve a carrier session")

    async def close(self) -> None:
        self.closed_count += 1
        if self.mutate_on == "close":
            self.ports.clear()


async def test_all_contract_checks_accept_valid_device_without_writes_or_carrier_operations():
    device = DeviceDouble()
    suite = DeviceContractTests()
    await suite.test_descriptor_matches_open_device(device)
    for key in CAPABILITIES:
        await suite.test_declared_capability_has_matching_port(device, key)
        await suite.test_lookup_requires_canonical_key(device, key)
    await suite.test_manifest_uses_catalog_and_scoped_evidence(device)
    await suite.test_verified_compatibility_has_device_evidence(device)
    await suite.test_description_preserves_identity_and_support(device)
    await suite.test_status_read_preserves_identity_and_support(device)
    await suite.test_inbox_scan_belongs_to_device(device)
    await suite.test_close_is_repeatable_and_preserves_support(device)
    assert device.closed_count == 2


@pytest.mark.parametrize("fault", ["missing", "undeclared", "wrong-interface"])
async def test_binding_contract_rejects_broken_adapter(fault):
    device = DeviceDouble()
    if fault == "missing":
        device.ports.pop(SMS_SEND)
        expected = "has no port"
    elif fault == "undeclared":
        device.manifest = replace(device.manifest, capabilities=(DEVICE_STATUS_READ.id,))
        expected = "Undeclared capability"
    else:
        device.ports[SMS_SEND] = object()
        expected = "wrong port interface"
    with pytest.raises(AssertionError, match=expected):
        await DeviceContractTests().test_declared_capability_has_matching_port(device, SMS_SEND)


async def test_noncanonical_lookup_is_rejected():
    class NoncanonicalDevice(DeviceDouble):
        def get[P](self, key: CapabilityKey[P]) -> P | None:
            return cast(P, self)

    with pytest.raises(AssertionError, match="noncanonical"):
        await DeviceContractTests().test_lookup_requires_canonical_key(
            NoncanonicalDevice(), DEVICE_STATUS_READ
        )


@pytest.mark.parametrize("fault", ["identity", "manifest"])
async def test_descriptor_must_match_open_device(fault):
    device = DeviceDouble()
    device.descriptor = DeviceDescriptor(
        CellularDeviceId("wrong") if fault == "identity" else device.device_id,
        replace(device.manifest, version="wrong") if fault == "manifest" else device.manifest,
    )
    with pytest.raises(AssertionError, match="logical device identity|manifest disagree"):
        await DeviceContractTests().test_descriptor_matches_open_device(device)


@pytest.mark.parametrize(
    "operation,test_name",
    [
        ("describe", "test_description_preserves_identity_and_support"),
        ("read", "test_status_read_preserves_identity_and_support"),
        ("scan", "test_inbox_scan_belongs_to_device"),
        ("close", "test_close_is_repeatable_and_preserves_support"),
    ],
)
async def test_operations_cannot_change_identity_manifest_or_supported_ports(operation, test_name):
    device = DeviceDouble()
    device.mutate_on = operation
    with pytest.raises(AssertionError, match="changed device identity, manifest or support"):
        await getattr(DeviceContractTests(), test_name)(device)


async def test_foreign_inbox_source_is_rejected():
    device = DeviceDouble()
    device.snapshot_device_id = CellularDeviceId("other")
    with pytest.raises(AssertionError, match="another device"):
        await DeviceContractTests().test_inbox_scan_belongs_to_device(device)


@pytest.mark.parametrize("operation", ["read", "scan"])
async def test_vendor_payload_cannot_replace_domain_observations(operation):
    class VendorPayloadPort:
        async def read(self):
            return {"raw": "vendor"}

        async def scan(self):
            return {"messages": []}

    device = DeviceDouble()
    device.ports[DEVICE_STATUS_READ] = VendorPayloadPort()
    device.ports[SMS_INBOX_READ] = VendorPayloadPort()
    suite = DeviceContractTests()
    with pytest.raises(AssertionError, match="must return"):
        if operation == "read":
            await suite.test_status_read_preserves_identity_and_support(device)
        else:
            await suite.test_inbox_scan_belongs_to_device(device)


@pytest.mark.parametrize("fault", ["fixture-only", "wrong-variant", "missing-variant", "incomplete"])
async def test_verified_claim_requires_matching_device_evidence_for_every_capability(fault):
    device = DeviceDouble()
    variant = DeviceVariant("fixture-firmware", "fixture-hardware", "fixture-mode")
    evidence = CompatibilityEvidence(
        DeviceVariant("other") if fault == "wrong-variant" else variant,
        VerificationKind.PROTOCOL_FIXTURE
        if fault == "fixture-only"
        else VerificationKind.DEVICE_VERIFICATION,
        "Synthetic evidence, never hardware verification",
        (DEVICE_STATUS_READ.id,) if fault == "incomplete" else device.manifest.capabilities,
    )
    device.manifest = replace(device.manifest, compatibility_evidence=(evidence,))
    device.descriptor = DeviceDescriptor(
        device.device_id,
        device.manifest,
        DeviceObservation(
            datetime.now(UTC),
            Availability.READY,
            Compatibility.VERIFIED,
            variant=None if fault == "missing-variant" else variant,
        ),
    )
    with pytest.raises(AssertionError, match="Verified compatibility needs"):
        await DeviceContractTests().test_verified_compatibility_has_device_evidence(device)


async def test_separate_matching_device_evidence_can_cover_capabilities_together():
    device = DeviceDouble()
    variant = DeviceVariant("synthetic")
    device.manifest = replace(
        device.manifest,
        compatibility_evidence=tuple(
            CompatibilityEvidence(variant, VerificationKind.DEVICE_VERIFICATION, "Synthetic", (key.id,))
            for key in CAPABILITIES
        ),
    )
    device.descriptor = DeviceDescriptor(
        device.device_id,
        device.manifest,
        DeviceObservation(datetime.now(UTC), Availability.READY, Compatibility.VERIFIED, variant=variant),
    )
    await DeviceContractTests().test_verified_compatibility_has_device_evidence(device)


@pytest.mark.parametrize("fault", ["unknown-capability", "blank-reference", "undeclared-evidence"])
async def test_manifest_checks_reject_incoherent_declarations(fault):
    device = DeviceDouble()
    if fault == "unknown-capability":
        device.manifest = replace(device.manifest, capabilities=(cast(CapabilityId, "invented"),))
    else:
        device.manifest = replace(
            device.manifest,
            capabilities=(DEVICE_STATUS_READ.id,),
            compatibility_evidence=(
                CompatibilityEvidence(
                    DeviceVariant("synthetic"),
                    VerificationKind.PROTOCOL_FIXTURE,
                    " " if fault == "blank-reference" else "Synthetic",
                    (CARRIER_BALANCE_READ.id,)
                    if fault == "undeclared-evidence"
                    else (DEVICE_STATUS_READ.id,),
                ),
            ),
        )
    with pytest.raises(AssertionError, match="unknown capability|needs a reference|undeclared capability"):
        await DeviceContractTests().test_manifest_uses_catalog_and_scoped_evidence(device)


@pytest.mark.parametrize("key", [DEVICE_STATUS_READ, SMS_INBOX_READ], ids=lambda key: key.id)
async def test_only_undeclared_read_capabilities_are_skipped(key):
    device = DeviceDouble()
    suite = DeviceContractTests()
    check = (
        suite.test_status_read_preserves_identity_and_support
        if key is DEVICE_STATUS_READ
        else suite.test_inbox_scan_belongs_to_device
    )
    device.ports.pop(key)
    with pytest.raises(AssertionError, match="has no port"):
        await check(device)
    device.manifest = replace(device.manifest, capabilities=tuple(k.id for k in CAPABILITIES if k is not key))
    with pytest.raises(pytest.skip.Exception, match="does not declare"):
        await check(device)
