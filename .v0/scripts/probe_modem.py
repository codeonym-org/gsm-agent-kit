"""Read-only modem probe. Prints status/counts, never SMS contents or phone numbers."""

import asyncio
import json
from dataclasses import asdict

import httpx

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
        modem = ZteModem(client, page_size=config.page_size, max_pages=config.max_pages)
        status = await modem.get_status()
        messages = await modem.list_messages()
        print(
            json.dumps(
                {
                    "status": asdict(status),
                    "received_messages": len(messages),
                    "complete_messages": sum(m.complete for m in messages),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
