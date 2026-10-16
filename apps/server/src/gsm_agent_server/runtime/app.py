import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from dishka import Provider
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from gsm_agent.application.errors import (
    DeviceNotFoundError,
    DeviceQueryTimeoutError,
    UnsupportedCapabilityError,
)
from gsm_agent.application.inbox import InboxDeadlineError, InboxDisabledError
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent_core.domain.devices import DeviceReadIssue
from gsm_agent_core.domain.sms import InboxReadError

from gsm_agent_server.api.routes import router
from gsm_agent_server.di.container import build_container
from gsm_agent_server.runtime.inbox import poll_inboxes
from gsm_agent_server.runtime.settings import Settings


def create_app(settings: Settings | None = None, *overrides: Provider) -> FastAPI:
    config = settings or Settings()
    container = build_container(config, *overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        polling: asyncio.Task[None] | None = None
        try:
            # Compose eagerly: invalid selections fail startup, not the first request.
            await container.get(DeviceDirectory)
            if config.inbox.enabled:
                await container.get(InboxStore)
                polling = asyncio.create_task(poll_inboxes(container, config.inbox), name="inbox-polling")
            yield
        finally:
            try:
                if polling is not None:
                    polling.cancel()
                    with suppress(asyncio.CancelledError):
                        await polling
            finally:
                await container.close()

    app = FastAPI(title="GSM Agent Kit", version="0.1.0", lifespan=lifespan)
    app.state.settings = config
    setup_dishka(container=container, app=app)
    app.include_router(router)

    async def query_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, UnsupportedCapabilityError):
            return JSONResponse(status_code=501, content={"detail": str(exc), "capability": exc.capability})
        code = 404 if isinstance(exc, DeviceNotFoundError) else 504
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    for error in (DeviceNotFoundError, UnsupportedCapabilityError, DeviceQueryTimeoutError):
        app.add_exception_handler(error, query_error)

    async def inbox_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, InboxReadError):
            status = 504 if exc.issue is DeviceReadIssue.TIMEOUT else 502
            return JSONResponse(status_code=status, content={"detail": str(exc), "issue": exc.issue.value})
        return JSONResponse(
            status_code=503 if isinstance(exc, InboxDisabledError) else 504, content={"detail": str(exc)}
        )

    for error in (InboxReadError, InboxDisabledError, InboxDeadlineError):
        app.add_exception_handler(error, inbox_error)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "adapter_profile": config.device.adapter}

    return app
