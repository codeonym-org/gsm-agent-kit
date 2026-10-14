from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AgentInput:
    messages: tuple[ChatMessage, ...]
    thread_id: str | None = None

    def __post_init__(self) -> None:
        if not self.messages or not any(m.content.strip() for m in self.messages):
            raise ValueError("Agent input needs a nonempty message")


@dataclass(frozen=True)
class ReplyDecision:
    """The framework-independent structured output of the SMS assistant."""

    action: Literal["reply", "ignore"]
    text: str
    ignore_reason: (
        Literal["spam", "automated_notification", "unavailable_information", "unsupported_request"] | None
    ) = None

    def __post_init__(self) -> None:
        if self.action not in ("reply", "ignore"):
            raise ValueError("Unknown reply action")
        if self.action == "reply" and not self.text.strip():
            raise ValueError("A reply needs text")


def require_answer(decision: ReplyDecision) -> ReplyDecision:
    """Silence is only justified by an explicit spam/automation classification."""
    if decision.action == "reply" or decision.ignore_reason in ("spam", "automated_notification"):
        return decision
    if decision.ignore_reason == "unavailable_information":
        text = (
            "I can't check live news or other real-time information here. "
            "Ask about a specific topic and I can help explain it."
        )
    else:
        text = "I couldn't answer that request reliably. Please rephrase it or ask a more specific question."
    return ReplyDecision("reply", text)


@dataclass(frozen=True)
class AgentStreamEvent:
    """A text fragment or the final validated decision; never a LangChain object."""

    kind: Literal["text", "result"]
    text: str = ""
    result: ReplyDecision | None = None
