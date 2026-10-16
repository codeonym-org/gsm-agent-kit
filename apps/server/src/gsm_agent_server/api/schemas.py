from datetime import datetime
from typing import Self
from uuid import UUID

from gsm_agent.application.inbox import InboxRecord
from gsm_agent.application.submissions import SubmissionPart, SubmissionRecord
from gsm_agent_core.domain.balance import BalanceIssue
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
from gsm_agent_core.domain.sms import SmsAddress
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str
    capability: CapabilityId | None = None
    issue: DeviceReadIssue | BalanceIssue | None = None


class SendSmsRequest(BaseModel):
    request_id: UUID
    destination: str = Field(pattern=r"^\+[1-9][0-9]{2,14}$")
    text: str = Field(min_length=1, max_length=10000)


class SubmissionResponse(BaseModel):
    device_id: str
    request_id: UUID
    destination: str
    truncated: bool
    accepted_parts: int
    complete: bool
    blocked: bool
    created_at: datetime
    parts: tuple[SubmissionPart, ...]

    @classmethod
    def from_domain(cls, record: SubmissionRecord) -> Self:
        return cls(
            device_id=record.device_id.value,
            request_id=record.request_id,
            destination=record.destination.value,
            truncated=record.truncated,
            accepted_parts=record.accepted_parts,
            complete=record.complete,
            blocked=record.blocked,
            created_at=record.created_at,
            parts=record.parts,
        )


class InboxRecordResponse(BaseModel):
    id: str
    device_id: str
    storage_generation: str
    storage: str
    subscription_generation: str
    subscription_uncertain: bool
    provider_id: str
    sender: SmsAddress
    body: str
    provider_timestamp: str
    complete: bool
    baselined: bool
    replyable: bool
    observed_at: datetime

    @classmethod
    def from_domain(cls, record: InboxRecord) -> Self:
        return cls(
            id=record.id,
            device_id=record.source.device_id.value,
            storage_generation=record.source.storage_generation,
            storage=record.source.storage,
            subscription_generation=record.subscription_generation,
            subscription_uncertain=record.subscription_uncertain,
            provider_id=record.item.provider_id,
            sender=record.item.sender,
            body=record.item.body,
            provider_timestamp=record.item.provider_timestamp,
            complete=record.item.complete,
            baselined=record.baselined,
            replyable=record.replyable,
            observed_at=record.observed_at,
        )


class IngestResponse(BaseModel):
    observed: int
    queued: int
    baselined: bool


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
