from dataclasses import dataclass

from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.ports.runtime import RuntimeStatusReader
from gsm_agent.application.runtime import RuntimeStatus


@query
@dataclass(frozen=True)
class GetRuntimeStatus(Query[RuntimeStatus]):
    """Observe the runtime without initiating device or workflow operations."""


@query_handler
class GetRuntimeStatusHandler:
    def __init__(self, runtime: RuntimeStatusReader) -> None:
        self.runtime = runtime

    async def handle(self, request: GetRuntimeStatus) -> RuntimeStatus:
        return await self.runtime.read()
