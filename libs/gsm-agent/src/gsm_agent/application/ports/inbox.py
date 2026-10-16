from typing import Protocol

from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxSnapshot

from gsm_agent.application.inbox import InboxRecord, IngestResult


class InboxStore(Protocol):
    async def get(self, record_id: str) -> InboxRecord | None: ...

    async def ingest(self, snapshot: InboxSnapshot) -> IngestResult:
        """Atomically store observations, source baseline and outgoing events."""
        ...

    async def pending_events(self, device_id: CellularDeviceId, limit: int = 100) -> tuple[str, ...]: ...

    async def acknowledge_event(self, record_id: str) -> None: ...

    async def list_records(
        self, device_id: CellularDeviceId, *, limit: int, offset: int
    ) -> tuple[InboxRecord, ...]: ...
