from datetime import datetime
from typing import Self

from gsm_agent_core.domain.devices import (
    AdapterManifest,
    Availability,
    CapabilityId,
    CompatibilityEvidence,
    DeviceDescriptor,
    DeviceObservation,
    DeviceReadIssue,
    DeviceStatus,
)
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    capability: CapabilityId | None = None


class AdapterResponse(BaseModel):
    adapter_id: str
    version: str
    manufacturer: str
    model: str
    capabilities: tuple[CapabilityId, ...]
    required_transports: tuple[str, ...]
    runtime_dependencies: tuple[str, ...]
    compatibility_evidence: tuple[CompatibilityEvidence, ...]

    @classmethod
    def from_domain(cls, manifest: AdapterManifest) -> Self:
        return cls(
            adapter_id=manifest.adapter_id,
            version=manifest.version,
            manufacturer=manifest.model.manufacturer,
            model=manifest.model.name,
            capabilities=manifest.capabilities,
            required_transports=manifest.required_transports,
            runtime_dependencies=manifest.runtime_dependencies,
            compatibility_evidence=manifest.compatibility_evidence,
        )


class DeviceResponse(BaseModel):
    device_id: str
    adapter: AdapterResponse
    observation: DeviceObservation | None

    @classmethod
    def from_domain(cls, descriptor: DeviceDescriptor) -> Self:
        return cls(
            device_id=descriptor.device_id.value,
            adapter=AdapterResponse.from_domain(descriptor.adapter),
            observation=descriptor.observation,
        )


class StatusResponse(BaseModel):
    availability: Availability
    observed_at: datetime
    network_provider: str | None
    network_type: str | None
    signal_percent: int | None
    issue: DeviceReadIssue | None

    @classmethod
    def from_domain(cls, status: DeviceStatus) -> Self:
        return cls(
            availability=status.availability,
            observed_at=status.observed_at,
            network_provider=status.network_provider,
            network_type=status.network_type,
            signal_percent=status.signal_percent,
            issue=status.issue,
        )
