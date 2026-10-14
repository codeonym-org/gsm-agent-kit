"""SMS budgets and natural break points, independent of LLM/token splitters."""

import re
import unicodedata
from dataclasses import dataclass

GSM_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM_EXTENDED = frozenset("\f^{}\\[~]|€")


def sms_encoding(text: str) -> str:
    return "GSM7_default" if all(c in GSM_BASIC or c in GSM_EXTENDED for c in text) else "UNICODE"


def sms_units(text: str, encoding: str | None = None) -> int:
    encoding = encoding or sms_encoding(text)
    if encoding == "GSM7_default":
        return sum(2 if c in GSM_EXTENDED else 1 for c in text)
    return len(text.encode("utf-16-be")) // 2


def single_sms_capacity(encoding: str) -> int:
    return 160 if encoding == "GSM7_default" else 70


@dataclass(frozen=True)
class ReplyLimits:
    max_reply_chars: int = 240
    max_sms_parts: int = 3

    def __post_init__(self) -> None:
        if self.max_reply_chars < 8 or not 1 <= self.max_sms_parts <= 9:
            raise ValueError("Reply limits require at least 8 characters and 1–9 SMS parts")


@dataclass(frozen=True)
class MemoryLimits:
    max_messages: int = 20
    max_chars: int = 6000


@dataclass(frozen=True)
class SmsPlan:
    text: str
    parts: tuple[str, ...]


def _fit(text: str, budget: int, encoding: str | None) -> int:
    used = 0
    index = 0
    for c in text:
        size = 1 if encoding is None else sms_units(c, encoding)
        if used + size > budget:
            break
        used += size
        index += 1
    # Do not leave a combining mark detached from its base letter.
    if index < len(text) and unicodedata.combining(text[index]):
        while index > 0 and unicodedata.combining(text[index]):
            index -= 1
    return index


def _boundary(text: str, maximum: int) -> int:
    prefix = text[:maximum]
    # Avoid tiny chunks when an early paragraph/sentence is followed by a long one.
    minimum = max(1, maximum // 2)
    patterns = (r"\n\s*\n", r"[.!?؟。][\"')]*\s+", r"\s+")
    for pattern in patterns:
        breaks = [m.end() for m in re.finditer(pattern, prefix) if m.end() >= minimum]
        if breaks:
            return breaks[-1]
    return maximum


def _shorten(text: str, budget: int, encoding: str | None = None) -> str:
    size = len(text) if encoding is None else sms_units(text, encoding)
    if size <= budget:
        return text
    marker = "..."
    maximum = _fit(text, budget - len(marker), encoding)
    end = _boundary(text, maximum)
    return text[:end].rstrip() + marker


def plan_sms(text: str, limits: ReplyLimits) -> SmsPlan:
    """Cap plain text, split at natural breaks, and count numbering in each SMS.

    Each part is a separate single-segment SMS. This deliberately avoids handing
    a large payload to the modem's arbitrary concatenated-SMS splitter.
    """
    text = text.strip()
    if not text or any(ord(c) > 0xFFFF or 0xD800 <= ord(c) <= 0xDFFF for c in text):
        raise ValueError("SMS needs nonempty BMP plain text")
    text = _shorten(text, limits.max_reply_chars)
    encoding = sms_encoding(text)
    capacity = single_sms_capacity(encoding)
    if sms_units(text, encoding) <= capacity:
        return SmsPlan(text, (text,))
    if limits.max_sms_parts == 1:
        text = _shorten(text, capacity, encoding)
        return SmsPlan(text, (text,))

    # max_sms_parts <= 9, so '(1/3) ' always occupies six units.
    payload_budget = capacity - 6
    bodies = []
    position = 0
    final_text = text
    for part in range(limits.max_sms_parts):
        while position < len(text) and text[position].isspace():
            position += 1
        remaining = text[position:]
        if sms_units(remaining, encoding) <= payload_budget:
            bodies.append(remaining)
            break
        if part == limits.max_sms_parts - 1:
            body = _shorten(remaining, payload_budget, encoding)
            bodies.append(body)
            final_text = text[:position] + body
            break
        end = _boundary(remaining, _fit(remaining, payload_budget, encoding))
        if end == 0:
            raise ValueError("A text cluster cannot fit in one SMS")
        bodies.append(remaining[:end].rstrip())
        position += end
    total = len(bodies)
    parts = tuple(f"({i}/{total}) {body}" for i, body in enumerate(bodies, 1))
    return SmsPlan(final_text, parts)


def delivered_text(parts: tuple[str, ...]) -> str:
    """Conversation context contains payload text, without transport numbering."""
    return "\n".join(re.sub(r"^\([1-9]/[1-9]\) ", "", part) for part in parts)
