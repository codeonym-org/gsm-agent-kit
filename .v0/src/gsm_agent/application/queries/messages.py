from dataclasses import dataclass

from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.modem import ModemPort
from gsm_agent.domain.sms import InboxRecord, ModemStatus


@query
@dataclass(frozen=True)
class GetModemStatus(Query[ModemStatus]):
    pass


@query_handler
class GetModemStatusHandler:
    def __init__(self, modem: ModemPort):
        self.modem = modem

    async def handle(self, query: GetModemStatus) -> ModemStatus:
        return await self.modem.get_status()


@query
@dataclass(frozen=True)
class ListMessages(Query[list[InboxRecord]]):
    limit: int = 50


@query_handler
class ListMessagesHandler:
    def __init__(self, inbox: InboxStore):
        self.inbox = inbox

    async def handle(self, query: ListMessages) -> list[InboxRecord]:
        if not 1 <= query.limit <= 200:
            raise ValueError("Limit must be between 1 and 200")
        return await self.inbox.list_records(query.limit)
