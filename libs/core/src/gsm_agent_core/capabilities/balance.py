"""Exclusive, cancellation-cooperative carrier consultation ownership."""

from typing import Protocol, runtime_checkable

from gsm_agent_core.domain.balance import BalanceCarrier, BalanceObservation


class BalanceSession(Protocol):
    """An exclusive reservation; only this handle may release its own session.

    consult sends at most the carrier's fixed consultation request. It never
    follows a menu or retries. A response requesting continuation is returned as
    raw text, then close ends the owned session without choosing an option.
    close must release the local reservation even if network cleanup fails;
    uncertain network ownership must keep subsequent reservations busy.
    """

    async def consult(self, carrier: BalanceCarrier) -> BalanceObservation: ...

    async def close(self) -> None: ...


@runtime_checkable
class BalanceReader(Protocol):
    """Bind only when the adapter actually implements balance consultation.

    reserve acquires the device's shared operation ownership and checks for a
    foreign session. A foreign session raises BalanceReadError(BUSY), without
    cancellation. Reservation performs no USSD dispatch: ownership transfers
    only on successful return. Failure/cancellation leaves no local reservation.
    HTTP/serial encodings, response freshness and ownership tokens are adapter
    responsibilities. All methods must cooperate with asyncio cancellation.
    """

    async def reserve(self) -> BalanceSession: ...
