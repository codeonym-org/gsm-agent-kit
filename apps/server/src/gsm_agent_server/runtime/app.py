from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import Provider
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from gsm_agent.application.errors import (
    DeviceNotFoundError,
    DeviceQueryTimeoutError,
    UnsupportedCapabilityError,
)
from gsm_agent.application.ports.devices import DeviceDirectory

from gsm_agent_server.api.routes import router
from gsm_agent_server.di.container import build_container
from gsm_agent_server.runtime.settings import Settings


def create_app(settings: Settings | None = None, *overrides: Provider) -> FastAPI:
    config = settings or Settings()
    container = build_container(config, *overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            # Compose eagerly: invalid selections fail startup, not the first request.
            await container.get(DeviceDirectory)
            yield
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "adapter_profile": config.device.adapter}

    return app
