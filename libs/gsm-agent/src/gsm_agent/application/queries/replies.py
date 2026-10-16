from dataclasses import dataclass

from gsm_agent_core.domain.devices import CellularDeviceId
from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.replies import ReplyJobStatus, ReplyPolicy


@dataclass(frozen=True, slots=True)
class AssistantStatus:
    auto_reply: bool
    dry_run: bool
    jobs: dict[str, int]


@query
@dataclass(frozen=True)
class GetAssistantStatus(Query[AssistantStatus]):
    device_id: CellularDeviceId


@query_handler
class GetAssistantStatusHandler:
    def __init__(self, devices: DeviceDirectory, replies: ReplyStore, policy: ReplyPolicy) -> None:
        self.devices, self.replies, self.policy = devices, replies, policy

    async def handle(self, request: GetAssistantStatus) -> AssistantStatus:
        self.devices.get(request.device_id)
        return AssistantStatus(
            self.policy.enabled, self.policy.dry_run, await self.replies.counts(request.device_id)
        )


@query
@dataclass(frozen=True)
class ListReplyJobs(Query[tuple[ReplyJobStatus, ...]]):
    device_id: CellularDeviceId
    limit: int = 50
    offset: int = 0


@query_handler
class ListReplyJobsHandler:
    def __init__(self, devices: DeviceDirectory, replies: ReplyStore) -> None:
        self.devices, self.replies = devices, replies

    async def handle(self, request: ListReplyJobs) -> tuple[ReplyJobStatus, ...]:
        self.devices.get(request.device_id)
        return await self.replies.list_jobs(request.device_id, limit=request.limit, offset=request.offset)
