from typing import Protocol

from gsm_agent.domain.agent import ChatMessage
from gsm_agent.domain.sms_text import MemoryLimits


class ConversationStore(Protocol):
    async def remember(self, thread_id: str, source_key: str, message: ChatMessage) -> None:
        """Idempotently persist a turn, keyed by thread, source, and role."""
        ...

    async def history(
        self, thread_id: str, limits: MemoryLimits, *, through_key: str | None = None
    ) -> tuple[ChatMessage, ...]:
        """Return bounded turns through the requested user turn, in chronological order."""
        ...
