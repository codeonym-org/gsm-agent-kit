"""In-memory worker observations; exception payloads are never retained."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from gsm_agent.application.inbox import InboxDeadlineError
from gsm_agent.application.runtime import RuntimeStatus, WorkerId, WorkerIssue, WorkerState, WorkerStatus
from gsm_agent_core.domain.devices import DeviceReadIssue
from gsm_agent_core.domain.sms import InboxReadError


def worker_issue(error: Exception) -> WorkerIssue:
    if isinstance(error, InboxReadError) and isinstance(error.issue, DeviceReadIssue):
        return error.issue
    if isinstance(error, (TimeoutError, InboxDeadlineError)):
        return DeviceReadIssue.TIMEOUT
    return "operation_failed"


class RuntimeMonitor:
    """One event-loop owner; immutable snapshots remain valid after later updates."""

    def __init__(
        self,
        *,
        inbox_enabled: bool,
        replies_enabled: bool,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._clock = clock
        self._started_at = clock()
        self._workers = {
            worker: WorkerStatus(worker, WorkerState.STARTING if enabled else WorkerState.DISABLED)
            for worker, enabled in ((WorkerId.INBOX, inbox_enabled), (WorkerId.REPLIES, replies_enabled))
        }

    async def read(self) -> RuntimeStatus:
        return RuntimeStatus(self._started_at, self._clock(), tuple(self._workers.values()))

    def begin(self, worker: WorkerId) -> None:
        previous = self._workers[worker]
        self._workers[worker] = replace(
            previous,
            state=WorkerState.RUNNING,
            iterations_started=previous.iterations_started + 1,
            last_attempt_at=self._clock(),
        )

    def succeeded(self, worker: WorkerId) -> None:
        previous = self._workers[worker]
        self._workers[worker] = replace(
            previous,
            state=WorkerState.WAITING,
            iterations_succeeded=previous.iterations_succeeded + 1,
            consecutive_failures=0,
            last_success_at=self._clock(),
        )

    def failed(self, worker: WorkerId, issue: WorkerIssue) -> None:
        previous = self._workers[worker]
        self._workers[worker] = replace(
            previous,
            state=WorkerState.DEGRADED,
            iterations_failed=previous.iterations_failed + 1,
            consecutive_failures=previous.consecutive_failures + 1,
            last_failure_at=self._clock(),
            last_issue=issue,
        )

    def exited(self, worker: WorkerId, *, cancelled: bool) -> None:
        previous = self._workers[worker]
        self._workers[worker] = replace(
            previous,
            state=WorkerState.STOPPED if cancelled else WorkerState.FAILED,
            last_failure_at=previous.last_failure_at if cancelled else self._clock(),
            last_issue=previous.last_issue if cancelled else "unexpected_exit",
        )
