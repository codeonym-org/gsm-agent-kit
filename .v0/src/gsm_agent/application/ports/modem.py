from typing import Protocol

from gsm_agent.domain.balance import BalanceCode, BalanceResult
from gsm_agent.domain.sms import ModemStatus, PhoneNumber, SmsMessage


class ModemPort(Protocol):
    async def consult_balance(self, code: BalanceCode) -> BalanceResult:
        """Run a single USSD balance consultation; never auto-select menu options."""
        ...

    async def get_status(self) -> ModemStatus: ...

    async def list_messages(self) -> list[SmsMessage]:
        """Return a complete inbox snapshot or raise; never a truncated snapshot."""
        ...

    async def send_sms(self, recipient: PhoneNumber, message: str) -> None:
        """Wait for send completion, or raise explicit failure/uncertain outcome."""
        ...
