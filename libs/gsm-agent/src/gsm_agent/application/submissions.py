import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import identity_digest
from gsm_agent_core.domain.submission import SmsDestination, SmsEncoding, SubmissionOutcome, SubmissionReason

from gsm_agent.application.text import SmsLimits


class PartState(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    NOT_SUBMITTED = "not_submitted"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SubmissionAttempt:
    id: str
    outcome: SubmissionOutcome | None
    reason: SubmissionReason | None
    provider_reference: str | None
    started_at: datetime


@dataclass(frozen=True, slots=True)
class SubmissionPart:
    message_id: str
    index: int
    text: str
    encoding: SmsEncoding
    state: PartState
    attempts: tuple[SubmissionAttempt, ...]


@dataclass(frozen=True, slots=True)
class SubmissionRecord:
    device_id: CellularDeviceId
    request_id: UUID
    destination: SmsDestination
    request_digest: str
    truncated: bool
    created_at: datetime
    parts: tuple[SubmissionPart, ...]

    @property
    def accepted_parts(self) -> int:
        return sum(part.state is PartState.ACCEPTED for part in self.parts)

    @property
    def complete(self) -> bool:
        return self.accepted_parts == len(self.parts)

    @property
    def blocked(self) -> bool:
        return any(
            part.state in (PartState.REJECTED, PartState.UNKNOWN, PartState.IN_PROGRESS)
            for part in self.parts
        )


def request_digest(destination: SmsDestination, text: str) -> str:
    return identity_digest(destination.value, text)


@dataclass(frozen=True, slots=True)
class SubmissionPolicy:
    limits: SmsLimits = SmsLimits()
    timeout_seconds: float = 100

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Submission timeout must be finite and positive")


class SubmissionCoordinator:
    def __init__(self) -> None:
        self._locks: dict[CellularDeviceId, asyncio.Lock] = {}

    def lock(self, device_id: CellularDeviceId) -> asyncio.Lock:
        return self._locks.setdefault(device_id, asyncio.Lock())


class SubmissionDisabledError(Exception):
    pass


class SubmissionConflictError(Exception):
    pass


class SubmissionNotFoundError(Exception):
    pass


class SubmissionDeadlineError(Exception):
    pass


class InvalidSmsError(Exception):
    pass
