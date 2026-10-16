"""A bounded observation, dispatched through QuerySender despite transport writes."""

import asyncio
import math
from dataclasses import dataclass

from gsm_agent_core.capabilities.balance import BalanceSession
from gsm_agent_core.capabilities.catalog import CARRIER_BALANCE_READ
from gsm_agent_core.domain.balance import BalanceCarrier, BalanceIssue, BalanceObservation, BalanceReadError
from gsm_agent_core.domain.devices import CellularDeviceId
from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.errors import DeviceQueryTimeoutError, UnsupportedCapabilityError
from gsm_agent.application.ports.devices import DeviceDirectory


@dataclass(frozen=True, slots=True)
class BalancePolicy:
    carrier: BalanceCarrier | None = None
    timeout_seconds: float = 30
    cleanup_timeout_seconds: float = 2

    def __post_init__(self) -> None:
        if self.carrier is not None and not isinstance(self.carrier, BalanceCarrier):
            raise ValueError("Use a reviewed carrier consultation policy")
        if any(
            not math.isfinite(value) or value <= 0
            for value in (self.timeout_seconds, self.cleanup_timeout_seconds)
        ):
            raise ValueError("Balance deadlines must be finite and positive")


class BalanceNotConfiguredError(Exception):
    def __init__(self) -> None:
        super().__init__("Configure GSM_BALANCE__CARRIER before consulting balance")


async def _release(session: BalanceSession, timeout: float) -> None:
    try:
        async with asyncio.timeout(timeout):
            await session.close()
    except Exception:
        raise BalanceReadError(BalanceIssue.CLEANUP_FAILED) from None


@query
@dataclass(frozen=True)
class ConsultBalance(Query[BalanceObservation]):
    device_id: CellularDeviceId


@query_handler
class ConsultBalanceHandler:
    def __init__(self, devices: DeviceDirectory, policy: BalancePolicy) -> None:
        self.devices = devices
        self.policy = policy

    async def handle(self, request: ConsultBalance) -> BalanceObservation:
        reader = self.devices.get(request.device_id).get(CARRIER_BALANCE_READ)
        if reader is None:
            raise UnsupportedCapabilityError(CARRIER_BALANCE_READ.id)
        if self.policy.carrier is None:
            raise BalanceNotConfiguredError()
        session: BalanceSession | None = None
        failed = False
        try:
            try:
                # Ownership acquisition, dispatch and response share one budget.
                async with asyncio.timeout(self.policy.timeout_seconds):
                    session = await reader.reserve()
                    return await session.consult(self.policy.carrier)
            except TimeoutError:
                raise DeviceQueryTimeoutError("Balance consultation exceeded its deadline") from None
            except ValueError:
                raise BalanceReadError(BalanceIssue.INVALID_RESPONSE) from None
        except BaseException:
            failed = True
            raise
        finally:
            if session is not None:
                # An acquired handle is released even on deadline/client cancellation.
                # Cleanup has its own small budget; preserve the original failure.
                cleanup = asyncio.create_task(_release(session, self.policy.cleanup_timeout_seconds))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    try:
                        await asyncio.shield(cleanup)
                    except BalanceReadError:
                        pass
                    raise
                except BalanceReadError:
                    if not failed:
                        raise
