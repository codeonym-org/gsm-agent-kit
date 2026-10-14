from dataclasses import dataclass

from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.ports.modem import ModemPort
from gsm_agent.domain.balance import BalanceCode, BalanceResult


@query
@dataclass(frozen=True)
class ConsultBalance(Query[BalanceResult]):
    pass


@query_handler
class ConsultBalanceHandler:
    def __init__(self, modem: ModemPort, code: BalanceCode):
        self.modem = modem
        self.code = code

    async def handle(self, query: ConsultBalance) -> BalanceResult:
        return await self.modem.consult_balance(self.code)
