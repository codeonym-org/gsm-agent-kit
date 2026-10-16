"""Immutable, framework-independent descriptions of cellular devices."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class CellularDeviceId:
    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", self.value):
            raise ValueError("Device ID must be 1–64 letters, digits, underscores or hyphens")


class CapabilityId(StrEnum):
    DEVICE_STATUS_READ = "device.status.read"
    SMS_INBOX_READ = "sms.inbox.read"
    SMS_SEND = "sms.send"


class Availability(StrEnum):
    READY = "ready"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class Compatibility(StrEnum):
    UNKNOWN = "unknown"
    UNTESTED = "untested"
    VERIFIED = "verified"
    MISMATCH = "mismatch"


class VerificationKind(StrEnum):
    PROTOCOL_FIXTURE = "protocol_fixture"
    DEVICE_VERIFICATION = "device_verification"


class DeviceReadIssue(StrEnum):
    OFFLINE = "offline"
    TIMEOUT = "timeout"
    AUTH_REQUIRED = "auth_required"
    INVALID_RESPONSE = "invalid_response"
    MODEL_MISMATCH = "model_mismatch"
    IDENTITY_UNKNOWN = "identity_unknown"


@dataclass(frozen=True, slots=True)
class DeviceVariant:
    firmware: str | None = None
    hardware_revision: str | None = None
    operating_mode: str | None = None


@dataclass(frozen=True, slots=True)
class CompatibilityEvidence:
    variant: DeviceVariant
    kind: VerificationKind
    reference: str
    capabilities: tuple[CapabilityId, ...] = ()


@dataclass(frozen=True, slots=True)
class DeviceModel:
    manufacturer: str
    name: str

    def __post_init__(self) -> None:
        if not self.manufacturer.strip() or not self.name.strip():
            raise ValueError("Device manufacturer and model must be specified")


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    adapter_id: str
    version: str
    model: DeviceModel
    capabilities: tuple[CapabilityId, ...]
    required_transports: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    compatibility_evidence: tuple[CompatibilityEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.adapter_id.strip() or not self.version.strip():
            raise ValueError("Adapter identity and version must be specified")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Adapter capabilities must be unique")


@dataclass(frozen=True, slots=True)
class DeviceObservation:
    observed_at: datetime
    availability: Availability
    compatibility: Compatibility
    observed_model: str | None = None
    variant: DeviceVariant | None = None
    issue: DeviceReadIssue | None = None

    def __post_init__(self) -> None:
        if self.observed_at.utcoffset() is None:
            raise ValueError("Observation time must include a timezone")


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    device_id: CellularDeviceId
    adapter: AdapterManifest
    observation: DeviceObservation | None = None


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    availability: Availability
    observed_at: datetime
    network_provider: str | None = None
    network_type: str | None = None
    signal_percent: int | None = None
    issue: DeviceReadIssue | None = None

    def __post_init__(self) -> None:
        if self.observed_at.utcoffset() is None:
            raise ValueError("Observation time must include a timezone")
        if self.signal_percent is not None and not 0 <= self.signal_percent <= 100:
            raise ValueError("Signal percentage must be between 0 and 100")
