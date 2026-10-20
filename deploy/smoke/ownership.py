"""A second real runtime must refuse the synthetic backend's shared volume."""

import asyncio

from backend import create_smoke_app
from gsm_agent_server.infra.state_ownership import StateAlreadyOwnedError


async def verify() -> None:
    app = create_smoke_app()
    try:
        async with app.router.lifespan_context(app):
            raise AssertionError("A competing backend unexpectedly acquired the shared state")
    except StateAlreadyOwnedError:
        print("PASS: second backend refused shared state before recovery/device access")


if __name__ == "__main__":
    asyncio.run(verify())
