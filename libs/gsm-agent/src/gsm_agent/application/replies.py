"""Reply workflow state and conversation policy, independent of AI and storage frameworks."""

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import phonenumbers
from gsm_agent_core.domain.sms import identity_digest
from gsm_agent_core.domain.submission import SmsDestination

from gsm_agent.application.inbox import InboxRecord


class ReplyState(StrEnum):
    QUEUED = "queued"
    GENERATING = "generating"
    PREPARED = "prepared"
    SUBMITTING = "submitting"
    COMPLETED = "completed"
    IGNORED = "ignored"
    DRY_RUN = "dry_run"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class ReplyPolicy:
    enabled: bool = False
    dry_run: bool = True
    default_region: str | None = None
    timeout_seconds: float = 60
    history_max_messages: int = 20
    history_max_chars: int = 6000
    history_retention_days: int = 30
    input_max_chars: int = 2000

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Agent deadline must be finite and positive")
        if self.default_region is not None and self.default_region not in phonenumbers.SUPPORTED_REGIONS:
            raise ValueError("Default phone region must be a supported ISO country code")
        if (
            self.history_max_messages < 2
            or self.history_max_chars < 1
            or self.history_retention_days < 1
            or self.input_max_chars < 1
        ):
            raise ValueError("Conversation limits must be positive and allow at least two messages")


@dataclass(frozen=True, slots=True)
class ReplyJob:
    record_id: str
    conversation_key: str
    request_id: UUID
    destination: SmsDestination
    state: ReplyState
    text: str
    issue: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReplyJobStatus:
    record_id: str
    request_id: UUID
    state: ReplyState
    issue: str | None
    created_at: datetime


class ReplyCoordinator:
    """Serialize background/manual drains and conversation ordering in one runtime owner."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()


class RepliesDisabledError(Exception):
    pass


def reply_destination(record: InboxRecord, region: str | None) -> SmsDestination | None:
    value = record.item.sender.value.strip()
    # Named senders and short codes never become paid destinations. Only phone syntax.
    if len(value) <= 6 or any(char not in "+0123456789 ().-" for char in value):
        return None
    if value.startswith("00"):
        value = "+" + value[2:]
    try:
        number = phonenumbers.parse(value, region)
        if not phonenumbers.is_possible_number(number) or number.extension:
            return None
        return SmsDestination(phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164))
    except (phonenumbers.NumberParseException, ValueError):
        return None


def conversation_key(record: InboxRecord, destination: SmsDestination) -> str:
    # Storage replacement is conservative: begin a new conversation as well as a new baseline.
    return identity_digest(record.source.key, record.subscription_generation, destination.value)
