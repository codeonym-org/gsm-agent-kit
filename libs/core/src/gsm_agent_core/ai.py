from collections.abc import AsyncIterator
from typing import Protocol

from gsm_agent_core.domain.agent import AgentInput, ReplyDecision


class AgentUnavailableError(Exception):
    """Sanitized provider failure; no credentials, prompts or provider payloads."""


class AIAgent(Protocol):
    async def invoke(self, request: AgentInput) -> ReplyDecision: ...

    def stream(self, request: AgentInput) -> AsyncIterator[ReplyDecision]:
        """Yield validated complete decisions, never raw structured-output tokens."""
        ...
