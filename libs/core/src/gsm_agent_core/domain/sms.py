"""Inbox observations, including incomplete messages that must never trigger replies."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from gsm_agent_core.domain.devices import CellularDeviceId, DeviceReadIssue


def identity_digest(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


class SmsAddressKind(StrEnum):
    INTERNATIONAL = "international"
    NATIONAL = "national"
    SHORT_CODE = "short_code"
    ALPHANUMERIC = "alphanumeric"


@dataclass(frozen=True, slots=True)
class SmsAddress:
    value: str
    kind: SmsAddressKind

    def __post_init__(self) -> None:
        if not self.value.strip() or len(self.value) > 128:
            raise ValueError("SMS address must contain 1–128 characters")

    @classmethod
    def from_sender(cls, value: str) -> "SmsAddress":
        # Preserve national numbers: no country or international identity is inferred.
        if re.fullmatch(r"\+[0-9]{3,15}", value):
            kind = SmsAddressKind.INTERNATIONAL
        elif re.fullmatch(r"[0-9]{1,6}", value):
            kind = SmsAddressKind.SHORT_CODE
        elif re.fullmatch(r"[0-9]{7,15}", value):
            kind = SmsAddressKind.NATIONAL
        else:
            kind = SmsAddressKind.ALPHANUMERIC
        return cls(value, kind)


@dataclass(frozen=True, slots=True)
class InboxSource:
    device_id: CellularDeviceId
    storage_generation: str
    storage: str

    def __post_init__(self) -> None:
        if any(not value.strip() or len(value) > 128 for value in (self.storage_generation, self.storage)):
            raise ValueError("Storage identity must contain 1–128 characters")

    @property
    def key(self) -> str:
        return identity_digest(self.device_id.value, self.storage_generation, self.storage)


@dataclass(frozen=True, slots=True)
class InboxItem:
    provider_id: str
    sender: SmsAddress
    body: str
    provider_timestamp: str
    complete: bool

    def __post_init__(self) -> None:
        if not self.provider_id or not self.provider_timestamp:
            raise ValueError("Stored SMS requires provider identity and timestamp evidence")

    @property
    def occurrence_evidence(self) -> str:
        # Excluding the body lets a partial message keep its identity as it grows.
        return identity_digest(self.provider_id, self.sender.kind, self.sender.value, self.provider_timestamp)


@dataclass(frozen=True, slots=True)
class InboxSnapshot:
    source: InboxSource
    subscription_generation: str
    started_at: datetime
    finished_at: datetime
    items: tuple[InboxItem, ...]

    def __post_init__(self) -> None:
        if self.started_at.utcoffset() is None or self.finished_at.utcoffset() is None:
            raise ValueError("Scan times must include timezones")
        if self.finished_at < self.started_at:
            raise ValueError("Scan completion precedes its start")
        if not self.subscription_generation.strip() or len(self.subscription_generation) > 128:
            raise ValueError("Subscription generation must contain 1–128 characters")
        if len({item.provider_id for item in self.items}) != len(self.items):
            raise ValueError("A snapshot cannot contain conflicting occurrences in the same slot")


class InboxReadError(Exception):
    """Normalized read failure; never includes provider payload or message content."""

    def __init__(self, issue: DeviceReadIssue) -> None:
        self.issue = issue
        super().__init__(f"Inbox scan failed: {issue.value}")
