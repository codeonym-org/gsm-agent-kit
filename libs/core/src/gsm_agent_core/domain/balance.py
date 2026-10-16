"""Carrier consultations are observations, never purchases or menu navigation."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class BalanceCarrier(StrEnum):
    INWI = "inwi"
    SIMULATED = "simulated"

    @property
    def consultation_code(self) -> str | None:
        # Reviewed consultation only; callers cannot supply arbitrary USSD codes.
        return "*120*30#" if self is BalanceCarrier.INWI else None


@dataclass(frozen=True, slots=True)
class CreditBalance:
    amount: Decimal
    currency: str
    conditions: str | None = None

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount < 0:
            raise ValueError("Credit must be a finite nonnegative amount")
        if (
            len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isalpha()
            or not self.currency.isupper()
        ):
            raise ValueError("Currency must be a three-letter uppercase code")


@dataclass(frozen=True, slots=True)
class SmsAllowance:
    remaining: int
    conditions: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.remaining, int) or isinstance(self.remaining, bool) or self.remaining < 0:
            raise ValueError("SMS allowance must be a nonnegative count")


@dataclass(frozen=True, slots=True)
class BalanceObservation:
    raw_text: str
    observed_at: datetime
    credit: CreditBalance | None = None
    sms_allowance: SmsAllowance | None = None

    def __post_init__(self) -> None:
        if not self.raw_text.strip() or len(self.raw_text) > 8192:
            raise ValueError("Carrier response must contain 1–8192 characters")
        if any(0xD800 <= ord(char) <= 0xDFFF or char == "\x00" for char in self.raw_text):
            raise ValueError("Invalid carrier response text")
        if self.observed_at.utcoffset() is None:
            raise ValueError("Observation time must include a timezone")


class BalanceIssue(StrEnum):
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    CLEANUP_FAILED = "cleanup_failed"


class BalanceReadError(Exception):
    def __init__(self, issue: BalanceIssue) -> None:
        super().__init__("Carrier balance consultation could not complete")
        self.issue = issue
