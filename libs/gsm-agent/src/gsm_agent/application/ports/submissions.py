from typing import Protocol
from uuid import UUID

from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import PreparedSms, SmsDestination, SmsSubmissionResult

from gsm_agent.application.submissions import SubmissionRecord
from gsm_agent.application.text import SmsPlan


class SubmissionStore(Protocol):
    async def create(
        self,
        device_id: CellularDeviceId,
        request_id: UUID,
        destination: SmsDestination,
        digest: str,
        plan: SmsPlan,
    ) -> SubmissionRecord:
        """Commit intent and immutable plan; conflicting reuse must raise SubmissionConflictError."""
        ...

    async def get(self, device_id: CellularDeviceId, request_id: UUID) -> SubmissionRecord | None: ...

    async def begin_attempt(
        self, device_id: CellularDeviceId, request_id: UUID, index: int
    ) -> PreparedSms | None:
        """Commit an attempt before I/O; accepted/uncertain/rejected parts cannot be retried."""
        ...

    async def finish_attempt(self, result: SmsSubmissionResult) -> None: ...

    async def interrupt(self, device_id: CellularDeviceId, request_id: UUID) -> None:
        """Quarantine in-progress attempts with unknown outcomes."""
        ...
