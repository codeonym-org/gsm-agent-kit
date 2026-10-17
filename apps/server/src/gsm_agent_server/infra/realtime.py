"""Best-effort, post-commit invalidations. Durable queries remain authoritative."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from gsm_agent.application.inbox import InboxRecord, IngestResult
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.ports.submissions import SubmissionStore
from gsm_agent.application.replies import ReplyJob, ReplyPolicy, ReplyState
from gsm_agent.application.submissions import SubmissionRecord
from gsm_agent.application.text import SmsPlan
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxSnapshot
from gsm_agent_core.domain.submission import PreparedSms, SmsDestination, SmsSubmissionResult


class ChangeFeed:
    """Single-process fanout with bounded queues; slow clients coalesce changes."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[int]] = set()
        self._revision = 0

    def publish(self) -> None:
        self._revision += 1
        for queue in self._subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(self._revision)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[int]]:
        queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        queue.put_nowait(self._revision)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


class ObservedInbox:
    def __init__(self, store: InboxStore, feed: ChangeFeed) -> None:
        self.store, self.feed = store, feed
        self.get = store.get
        self.pending_events = store.pending_events
        self.acknowledge_event = store.acknowledge_event
        self.list_records = store.list_records
        self._snapshots: dict[str, object] = {}

    async def ingest(self, snapshot: InboxSnapshot) -> IngestResult:
        result = await self.store.ingest(snapshot)
        identity = (snapshot.source, snapshot.subscription_generation, snapshot.items)
        key = snapshot.source.device_id.value
        if self._snapshots.get(key) != identity:
            self._snapshots[key] = identity
            self.feed.publish()
        return result


class ObservedReplies:
    def __init__(self, store: ReplyStore, feed: ChangeFeed) -> None:
        self.store, self.feed = store, feed
        self.history = store.history
        self.counts = store.counts
        self.list_jobs = store.list_jobs
        self.next_job = store.next_job

    async def enqueue(self, record: InboxRecord, destination: SmsDestination) -> None:
        await self.store.enqueue(record, destination)
        self.feed.publish()

    async def update(
        self, record_id: str, state: ReplyState, *, text: str = "", issue: str | None = None
    ) -> None:
        await self.store.update(record_id, state, text=text, issue=issue)
        self.feed.publish()

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
        await self.store.finish(job, state, user_text, accepted_text, policy, issue=issue)
        self.feed.publish()


class ObservedSubmissions:
    def __init__(self, store: SubmissionStore, feed: ChangeFeed) -> None:
        self.store, self.feed = store, feed
        self.get = store.get

    async def create(
        self,
        device_id: CellularDeviceId,
        request_id: UUID,
        destination: SmsDestination,
        digest: str,
        plan: SmsPlan,
    ) -> SubmissionRecord:
        result = await self.store.create(device_id, request_id, destination, digest, plan)
        self.feed.publish()
        return result

    async def begin_attempt(
        self, device_id: CellularDeviceId, request_id: UUID, index: int
    ) -> PreparedSms | None:
        result = await self.store.begin_attempt(device_id, request_id, index)
        self.feed.publish()
        return result

    async def interrupt(self, device_id: CellularDeviceId, request_id: UUID) -> None:
        await self.store.interrupt(device_id, request_id)
        self.feed.publish()

    async def finish_attempt(self, result: SmsSubmissionResult) -> None:
        await self.store.finish_attempt(result)
        self.feed.publish()
