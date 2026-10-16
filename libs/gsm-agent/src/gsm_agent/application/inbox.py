"""Durable ingestion state, independent of the persistence and transport frameworks."""

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime

from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxItem, InboxSource


@dataclass(frozen=True, slots=True)
class InboxRecord:
    id: str
    source: InboxSource
    item: InboxItem
    subscription_generation: str
    subscription_uncertain: bool
    baselined: bool
    observed_at: datetime

    @property
    def replyable(self) -> bool:
        return self.item.complete and not self.baselined and not self.subscription_uncertain


@dataclass(frozen=True, slots=True)
class IngestResult:
    observed: int
    queued: int
    baselined: bool


@dataclass(frozen=True, slots=True)
class InboxPolicy:
    timeout_seconds: float = 15

    def __post_init__(self) -> None:
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("Ingestion timeout must be finite and positive")


class IngestionCoordinator:
    """One owner per device; serialize scanning, ledger updates and outbox dispatch."""

    def __init__(self) -> None:
        self._locks: dict[CellularDeviceId, asyncio.Lock] = {}

    def lock(self, device_id: CellularDeviceId) -> asyncio.Lock:
        return self._locks.setdefault(device_id, asyncio.Lock())


class InboxDisabledError(Exception):
    pass


class InboxDeadlineError(Exception):
    pass
