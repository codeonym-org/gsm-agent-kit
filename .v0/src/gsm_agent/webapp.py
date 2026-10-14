import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gsm_agent.api.routes import router
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.di.container import build_container
from gsm_agent.domain.errors import (
    AgentUnavailableError,
    BalanceTimeoutError,
    BalanceUnavailableError,
    ModemConnectionError,
    SmsSendFailedError,
    SmsSendUncertainError,
)
from gsm_agent.runtime.listener import listen
from gsm_agent.runtime.settings import Settings
from gsm_agent.runtime.telemetry import configure_tracing


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    container = build_container(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=config.log_level)
        tracing = configure_tracing(config.trace_console)
        task = None
        try:
            await container.get(InboxStore)
            if config.listener.enabled:
                task = asyncio.create_task(listen(container, config.listener), name="sms-listener")
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await container.close()
            if tracing:
                tracing.shutdown()

    app = FastAPI(title="GSM Agent", version="0.1.0", lifespan=lifespan)
    app.state.settings = config
    setup_dishka(container=container, app=app)
    app.include_router(router)

    async def invalid(request: Request, exc: Exception):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    async def external_failure(request: Request, exc: Exception):
        uncertain = isinstance(exc, SmsSendUncertainError)
        return JSONResponse(
            status_code=504 if isinstance(exc, BalanceTimeoutError) else (503 if uncertain else 502),
            content={"detail": str(exc), "send_outcome": "uncertain" if uncertain else None},
        )

    app.add_exception_handler(ValueError, invalid)
    for error in (
        ModemConnectionError,
        AgentUnavailableError,
        SmsSendFailedError,
        SmsSendUncertainError,
        BalanceUnavailableError,
    ):
        app.add_exception_handler(error, external_failure)

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "listener_enabled": config.listener.enabled,
            "auto_reply": config.listener.auto_reply,
            "dry_run": config.listener.dry_run,
        }

    return app
