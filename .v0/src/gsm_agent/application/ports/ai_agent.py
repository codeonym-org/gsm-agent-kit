from collections.abc import AsyncIterator
from typing import Protocol

from gsm_agent.domain.agent import AgentInput, AgentStreamEvent, ReplyDecision


class AIAgent(Protocol):
    """Async execution; streams end in one validated structured result.

    Text events are previews, not SMS content. Only the result can be sent.
    Implementations own model configuration and framework-specific objects.
    """

    async def invoke(self, request: AgentInput) -> ReplyDecision: ...

    def stream(self, request: AgentInput) -> AsyncIterator[AgentStreamEvent]: ...
