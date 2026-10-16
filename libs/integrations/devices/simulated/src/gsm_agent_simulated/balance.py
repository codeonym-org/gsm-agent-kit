"""Synthetic consultation, with no network or carrier operations."""

import asyncio
from datetime import UTC, datetime

from gsm_agent_core.capabilities.balance import BalanceSession
from gsm_agent_core.domain.balance import BalanceCarrier, BalanceIssue, BalanceObservation, BalanceReadError


class SimulatedBalanceReader:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def reserve(self) -> BalanceSession:
        if self._lock.locked():
            raise BalanceReadError(BalanceIssue.BUSY)
        await self._lock.acquire()
        return _Session(self._lock)


class _Session:
    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock
        self._closed = False
        self._consulted = False

    async def consult(self, carrier: BalanceCarrier) -> BalanceObservation:
        if self._closed or self._consulted:
            raise BalanceReadError(BalanceIssue.UNAVAILABLE)
        self._consulted = True
        if carrier is not BalanceCarrier.SIMULATED:
            raise BalanceReadError(BalanceIssue.UNAVAILABLE)
        return BalanceObservation(
            "SIMULATED carrier response: account consultation example; no real balance available.",
            datetime.now(UTC),
        )

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._lock.release()
