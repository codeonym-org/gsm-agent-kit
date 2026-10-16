"""Single-segment SMS contracts. Acceptance is never evidence of recipient delivery."""

import re
from dataclasses import dataclass
from enum import StrEnum

GSM_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_EXTENDED = frozenset("\f^{}\\[~]|€")


class SmsEncoding(StrEnum):
    GSM7 = "gsm7"
    UCS2 = "ucs2"


def sms_encoding(text: str) -> SmsEncoding:
    return SmsEncoding.GSM7 if all(c in GSM_BASIC or c in GSM_EXTENDED for c in text) else SmsEncoding.UCS2


def sms_units(text: str, encoding: SmsEncoding) -> int:
    if encoding is SmsEncoding.GSM7:
        if any(c not in GSM_BASIC and c not in GSM_EXTENDED for c in text):
            raise ValueError("Text is not representable in GSM7")
        return sum(2 if c in GSM_EXTENDED else 1 for c in text)
    if any(ord(c) > 0xFFFF or 0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise ValueError("UCS2 requires BMP text without surrogates")
    return len(text)


@dataclass(frozen=True, slots=True)
class SmsDestination:
    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\+[1-9][0-9]{2,14}", self.value):
            raise ValueError("Destination must be an international number with a leading +")


@dataclass(frozen=True, slots=True)
class SmsSendConstraints:
    encodings: tuple[SmsEncoding, ...] = (SmsEncoding.GSM7, SmsEncoding.UCS2)
    gsm7_units: int = 160
    ucs2_units: int = 70

    def __post_init__(self) -> None:
        if not self.encodings or len(set(self.encodings)) != len(self.encodings):
            raise ValueError("SMS encodings must be nonempty and unique")
        if not 1 <= self.gsm7_units <= 160 or not 1 <= self.ucs2_units <= 70:
            raise ValueError("Invalid single-segment capacity")

    def capacity(self, encoding: SmsEncoding) -> int:
        if encoding not in self.encodings:
            raise ValueError("Encoding is unsupported by this adapter")
        return self.gsm7_units if encoding is SmsEncoding.GSM7 else self.ucs2_units

    def validate(self, text: str, encoding: SmsEncoding) -> None:
        if not text.strip() or sms_units(text, encoding) > self.capacity(encoding):
            raise ValueError("Text must fit one nonempty SMS segment")


@dataclass(frozen=True, slots=True)
class PreparedSms:
    message_id: str
    attempt_id: str
    destination: SmsDestination
    text: str
    encoding: SmsEncoding

    def __post_init__(self) -> None:
        if not self.message_id or not self.attempt_id:
            raise ValueError("Submission requires message and attempt identities")


class SubmissionOutcome(StrEnum):
    NOT_SUBMITTED = "not_submitted"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"


class SubmissionReason(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNAVAILABLE = "unavailable"
    AUTH_REQUIRED = "auth_required"
    MODEL_MISMATCH = "model_mismatch"
    BUSY = "busy"
    TIMEOUT = "timeout"
    DEVICE_REJECTED = "device_rejected"
    INVALID_RESPONSE = "invalid_response"
    TRANSPORT_ERROR = "transport_error"
    INTERRUPTED = "interrupted"
    ADAPTER_ERROR = "adapter_error"


@dataclass(frozen=True, slots=True)
class SmsSubmissionResult:
    message_id: str
    attempt_id: str
    outcome: SubmissionOutcome
    reason: SubmissionReason | None = None
    provider_reference: str | None = None
