"""Framework-independent conversation input and structured agent decisions."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class AgentInput:
    thread_id: str
    messages: tuple[ChatMessage, ...]


@dataclass(frozen=True, slots=True)
class ReplyDecision:
    action: Literal["reply", "ignore"]
    text: str = ""
    ignore_reason: Literal["spam", "automated_notification"] | None = None

    def __post_init__(self) -> None:
        if self.action == "reply":
            if not self.text.strip() or len(self.text) > 10000 or self.ignore_reason is not None:
                raise ValueError("A reply requires 1–10000 characters and no ignore reason")
        elif self.action == "ignore":
            if self.text or self.ignore_reason not in ("spam", "automated_notification"):
                raise ValueError("Ignore requires a spam or automated notification reason and no text")
        else:
            raise ValueError("Unknown agent decision")
