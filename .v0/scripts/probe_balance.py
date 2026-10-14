"""Run one configured USSD balance consultation. Sends no SMS or model requests."""

import asyncio
import json
from dataclasses import asdict

import httpx

from gsm_agent.domain.balance import BalanceCode
from gsm_agent.domain.errors import BalanceUnavailableError
from gsm_agent.infra.modem.zte import ZteModem
from gsm_agent.runtime.settings import Settings


async def main() -> None:
    config = Settings().modem
    async with httpx.AsyncClient(
        base_url=config.url,
        timeout=config.timeout,
        trust_env=False,
        headers={"Referer": config.url.rstrip("/") + "/index.html"},
    ) as client:
        modem = ZteModem(client, ussd_timeout=config.ussd_timeout)
        try:
            result = await modem.consult_balance(BalanceCode(config.balance_code))
        except BalanceUnavailableError as exc:
            print(json.dumps({"error": str(exc), "type": type(exc).__name__}))
            raise SystemExit(1) from None
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
