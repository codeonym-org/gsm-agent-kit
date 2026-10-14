import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class PhoneNumber:
    value: str

    def __post_init__(self) -> None:
        value = "".join(self.value.split())
        if value.startswith("00"):
            value = "+" + value[2:]
        if not re.fullmatch(r"\+?[0-9]{3,15}", value):
            raise ValueError("Recipient must contain 3–15 digits and an optional leading +")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class SmsMessage:
    modem_id: str
    sender: str
    content: str
    timestamp: str
    complete: bool = True

    @property
    def key(self) -> str:
        parts = (self.modem_id, self.sender, self.timestamp, self.content)
        # Length prefixes avoid collisions between different field boundaries.
        raw = "".join(f"{len(part)}:{part}" for part in parts)
        return hashlib.sha256(raw.encode()).hexdigest()


class MessageState(StrEnum):
    BASELINED = "baselined"
    OBSERVED = "observed"
    PENDING = "pending"
    PROCESSING = "processing"
    PLANNED = "planned"
    SENDING = "sending"
    SENT = "sent"
    DRY_RUN = "dry_run"
    IGNORED = "ignored"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class InboxRecord:
    message: SmsMessage
    state: MessageState
    reply: str | None = None
    attempts: int = 0
    error: str | None = None
    reply_parts: tuple[str, ...] = ()
    sent_parts: int = 0


@dataclass(frozen=True)
class ModemStatus:
    network_provider: str
    network_type: str
    signal_bars: int
    unread_sms_count: int


@dataclass(frozen=True)
class SendReceipt:
    recipient: str
    state: MessageState
    parts: int = 1


@dataclass(frozen=True)
class ReplyPolicy:
    enabled: bool = False
    dry_run: bool = True
    max_attempts: int = 3
