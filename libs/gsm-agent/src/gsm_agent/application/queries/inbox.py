from dataclasses import dataclass

from gsm_agent_core.domain.devices import CellularDeviceId
from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.inbox import InboxRecord
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore


@query
@dataclass(frozen=True)
class ListStoredMessages(Query[tuple[InboxRecord, ...]]):
    device_id: CellularDeviceId
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 200 or self.offset < 0:
            raise ValueError("Inbox page requires limit 1–200 and a nonnegative offset")


@query_handler
class ListStoredMessagesHandler:
    def __init__(self, devices: DeviceDirectory, inbox: InboxStore) -> None:
        self.devices, self.inbox = devices, inbox

    async def handle(self, request: ListStoredMessages) -> tuple[InboxRecord, ...]:
        self.devices.get(request.device_id)
        return await self.inbox.list_records(request.device_id, limit=request.limit, offset=request.offset)
