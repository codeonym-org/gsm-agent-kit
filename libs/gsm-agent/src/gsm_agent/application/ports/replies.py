from typing import Protocol

from gsm_agent_core.domain.agent import ChatMessage
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import SmsDestination

from gsm_agent.application.inbox import InboxRecord
from gsm_agent.application.replies import ReplyJob, ReplyJobStatus, ReplyPolicy, ReplyState


class ReplyStore(Protocol):
    async def enqueue(self, record: InboxRecord, destination: SmsDestination) -> None: ...

    async def next_job(self) -> ReplyJob | None: ...

    async def update(
        self, record_id: str, state: ReplyState, *, text: str = "", issue: str | None = None
    ) -> None: ...

    async def history(self, key: str, policy: ReplyPolicy) -> tuple[ChatMessage, ...]: ...

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
        """Atomically finalize a job and retain only evidence-backed history within limits."""
        ...

    async def counts(self, device_id: CellularDeviceId) -> dict[str, int]: ...

    async def list_jobs(
        self, device_id: CellularDeviceId, *, limit: int, offset: int
    ) -> tuple[ReplyJobStatus, ...]: ...
