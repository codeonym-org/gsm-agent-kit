"""Disabled services avoid importing optional integrations or opening databases."""

from collections.abc import AsyncIterator

from gsm_agent.application.inbox import InboxRecord
from gsm_agent.application.replies import (
    RepliesDisabledError,
    ReplyJob,
    ReplyJobStatus,
    ReplyPolicy,
    ReplyState,
)
from gsm_agent_core.ai import AgentUnavailableError
from gsm_agent_core.domain.agent import AgentInput, ChatMessage, ReplyDecision
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import SmsDestination


class DisabledReplyStore:
    async def enqueue(self, record: InboxRecord, destination: SmsDestination) -> None:
        raise RepliesDisabledError("Auto-reply is disabled")

    async def next_job(self) -> ReplyJob | None:
        return None

    async def update(
        self, record_id: str, state: ReplyState, *, text: str = "", issue: str | None = None
    ) -> None:
        raise RepliesDisabledError("Auto-reply is disabled")

    async def history(self, key: str, policy: ReplyPolicy) -> tuple[ChatMessage, ...]:
        return ()

    async def finish(
        self,
        job: ReplyJob,
        state: ReplyState,
        user_text: str,
        accepted_text: str,
        policy: ReplyPolicy,
        *,
        issue: str | None = None,
    ) -> None:
        raise RepliesDisabledError("Auto-reply is disabled")

    async def counts(self, device_id: CellularDeviceId) -> dict[str, int]:
        return {}

    async def list_jobs(
        self, device_id: CellularDeviceId, *, limit: int, offset: int
    ) -> tuple[ReplyJobStatus, ...]:
        return ()


class DisabledAgent:
    async def invoke(self, request: AgentInput) -> ReplyDecision:
        raise AgentUnavailableError("Auto-reply is disabled")

    async def stream(self, request: AgentInput) -> AsyncIterator[ReplyDecision]:
        raise AgentUnavailableError("Auto-reply is disabled")
        yield  # pragma: no cover
