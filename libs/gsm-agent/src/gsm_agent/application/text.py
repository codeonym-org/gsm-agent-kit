"""Application-owned plain-text normalization and bounded SMS planning."""

import re
import unicodedata
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser

import regex
from gsm_agent_core.domain.submission import SmsEncoding, SmsSendConstraints, sms_encoding, sms_units
from markdown_it import MarkdownIt
from markdown_it.token import Token


class _HtmlText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text: list[str] = []

    def handle_data(self, data: str) -> None:
        self.text.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("br", "p", "div", "li"):
            self.text.append("\n")


def _html_text(text: str) -> str:
    parser = _HtmlText()
    parser.feed(text)
    return "".join(parser.text)


class PlainTextNormalizer:
    def __init__(self):
        self.parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])

    def _inline(self, tokens: list[Token]) -> str:
        pieces: list[str] = []
        links: list[tuple[str, int]] = []
        for token in tokens:
            if token.type in ("text", "code_inline"):
                pieces.append(token.content)
            elif token.type in ("softbreak", "hardbreak"):
                pieces.append("\n")
            elif token.type == "image":
                pieces.append(self._inline(token.children or []))
            elif token.type == "link_open":
                links.append((str(token.attrGet("href") or ""), len(pieces)))
            elif token.type == "link_close" and links:
                url, start = links.pop()
                label = "".join(pieces[start:])
                if url and label != url:
                    pieces.append(f" ({url})")
            elif token.type == "html_inline":
                pieces.append(_html_text(token.content))
        return "".join(pieces)

    def normalize(self, text: str) -> str:
        pieces = []
        for token in self.parser.parse(text):
            if token.type == "inline":
                pieces.append(self._inline(token.children or []))
            elif token.type in ("fence", "code_block"):
                pieces.append(token.content + "\n\n")
            elif token.type == "html_block":
                pieces.append(_html_text(token.content) + "\n\n")
            elif token.type in ("paragraph_close", "heading_close"):
                pieces.append("\n\n")
            elif token.type in ("tr_close", "list_item_close", "hr"):
                pieces.append("\n")
            elif token.type in ("td_close", "th_close"):
                pieces.append("; ")
        text = unescape("".join(pieces))
        text = text.translate(
            str.maketrans(
                {
                    "‘": "'",
                    "’": "'",
                    "“": '"',
                    "”": '"',
                    "–": "-",
                    "—": "-",
                    "…": "...",
                    "\u00a0": " ",
                    "\r": "\n",
                    "\t": " ",
                }
            )
        )
        text = "".join(c for c in text if c == "\n" or unicodedata.category(c) not in ("Cc", "Cf"))
        text = unicodedata.normalize("NFC", text)
        lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


@dataclass(frozen=True, slots=True)
class SmsLimits:
    max_total_chars: int = 240
    max_parts: int = 3

    def __post_init__(self) -> None:
        if not 16 <= self.max_total_chars <= 10000 or not 1 <= self.max_parts <= 9:
            raise ValueError("SMS limits require 16–10000 total characters and 1–9 parts")


@dataclass(frozen=True, slots=True)
class SmsPlan:
    parts: tuple[str, ...]
    encoding: SmsEncoding
    truncated: bool


def _fit(text: str, budget: int, encoding: SmsEncoding | None = None) -> int:
    used, end = 0, 0
    for match in regex.finditer(r"\X", text):
        cluster = match.group()
        size = len(cluster) if encoding is None else sms_units(cluster, encoding)
        if used + size > budget:
            break
        used += size
        end = match.end()
    return end


def _boundary(text: str, maximum: int) -> int:
    # Paragraphs, sentences, words; fall back to a grapheme boundary for a long word.
    minimum = max(1, maximum // 2)
    boundaries = {match.end() for match in regex.finditer(r"\X", text[:maximum])}
    for pattern in (r"\n\s*\n", r"[.!?؟。][\"')]*\s+", r"\s+"):
        breaks = [
            match.end()
            for match in re.finditer(pattern, text[:maximum])
            if match.end() >= minimum and match.end() in boundaries
        ]
        if breaks:
            return breaks[-1]
    return maximum


def _lstrip_clusters(text: str) -> str:
    end = 0
    for match in regex.finditer(r"\X", text):
        if not match.group().isspace():
            break
        end = match.end()
    return text[end:]


def _shorten(text: str, budget: int, encoding: SmsEncoding | None = None) -> str:
    size = len(text) if encoding is None else sms_units(text, encoding)
    if size <= budget:
        return text
    marker = "..."
    if budget < len(marker):
        raise ValueError("SMS budget is too small")
    end = _boundary(text, _fit(text, budget - len(marker), encoding))
    if not end:
        raise ValueError("A text cluster cannot fit the SMS budget")
    return text[:end].rstrip() + marker


def prepare_sms(text: str, limits: SmsLimits, constraints: SmsSendConstraints) -> SmsPlan:
    normalized = PlainTextNormalizer().normalize(text)
    if not normalized:
        raise ValueError("SMS requires nonempty plain text")
    encoding = sms_encoding(normalized)
    # Validate all input, including text beyond the cap; unsupported Unicode is explicit.
    sms_units(normalized, encoding)
    capacity = constraints.capacity(encoding)
    capped = _shorten(normalized, limits.max_total_chars)
    if sms_units(capped, encoding) <= capacity:
        return SmsPlan((capped,), encoding, capped != normalized)
    if limits.max_parts == 1:
        capped = _shorten(capped, capacity, encoding)
        return SmsPlan((capped,), encoding, capped != normalized)
    for count in range(2, limits.max_parts + 1):
        # One-digit counts, six characters per prefix. Count them in both budgets.
        payload = _shorten(normalized, limits.max_total_chars - 6 * count)
        remaining, bodies = payload, []
        budget = capacity - 6
        while remaining and len(bodies) < count:
            if sms_units(remaining, encoding) <= budget:
                bodies.append(remaining)
                remaining = ""
            elif len(bodies) == count - 1:
                if count != limits.max_parts:
                    break
                bodies.append(_shorten(remaining, budget, encoding))
                remaining = ""
            else:
                end = _boundary(remaining, _fit(remaining, budget, encoding))
                if not end:
                    raise ValueError("A text cluster cannot fit one SMS")
                bodies.append(remaining[:end].rstrip())
                remaining = _lstrip_clusters(remaining[end:])
        if remaining:
            continue
        total = len(bodies)
        parts = tuple(f"({i}/{total}) {body}" for i, body in enumerate(bodies, 1))
        for part in parts:
            constraints.validate(part, encoding)
        # A suffix in the original is not a truncation; compare the represented payload.
        represented = " ".join(bodies).split()
        truncated = payload != normalized or represented != payload.split()
        return SmsPlan(parts, encoding, truncated)
    raise ValueError("SMS cannot fit the configured limits")
