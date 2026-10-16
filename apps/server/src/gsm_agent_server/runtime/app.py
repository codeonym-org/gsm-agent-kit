import asyncio
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
from gsm_agent.application.inbox import InboxDeadlineError, InboxDisabledError
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.ports.submissions import SubmissionStore
from gsm_agent.application.queries.balance import BalanceNotConfiguredError
from gsm_agent.application.submissions import (
    InvalidSmsError,
    SubmissionConflictError,
    SubmissionDeadlineError,
    SubmissionDisabledError,
    SubmissionNotFoundError,
)
from gsm_agent_core.ai import AIAgent
from gsm_agent_core.domain.balance import BalanceIssue, BalanceReadError
from gsm_agent_core.domain.devices import DeviceReadIssue
from gsm_agent_core.domain.sms import InboxReadError

from gsm_agent_server.api.routes import router
from gsm_agent_server.di.container import build_container
from gsm_agent_server.runtime.inbox import poll_inboxes
from gsm_agent_server.runtime.replies import process_replies
from gsm_agent_server.runtime.settings import Settings


def create_app(settings: Settings | None = None, *overrides: Provider) -> FastAPI:
    config = settings or Settings()
    container = build_container(config, *overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        polling: asyncio.Task[None] | None = None
        replying: asyncio.Task[None] | None = None
        try:
            # Compose eagerly: invalid selections fail startup, not the first request.
            await container.get(DeviceDirectory)
            if config.submissions.enabled:
                await container.get(SubmissionStore)
            if config.inbox.enabled:
                await container.get(InboxStore)
            if config.assistant.enabled:
                await container.get(ReplyStore)
                await container.get(AIAgent)
                replying = asyncio.create_task(
                    process_replies(container, config.assistant), name="sms-replies"
                )
            if config.inbox.enabled:
                polling = asyncio.create_task(poll_inboxes(container, config.inbox), name="inbox-polling")
            yield
        finally:
            try:
                tasks = [task for task in (polling, replying) if task is not None]
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
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

    async def balance_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, BalanceReadError):
            code = {
                BalanceIssue.BUSY: 409,
                BalanceIssue.UNAVAILABLE: 503,
                BalanceIssue.INVALID_RESPONSE: 502,
                BalanceIssue.CLEANUP_FAILED: 502,
            }[exc.issue]
            return JSONResponse(status_code=code, content={"detail": str(exc), "issue": exc.issue.value})
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    for error in (BalanceReadError, BalanceNotConfiguredError):
        app.add_exception_handler(error, balance_error)

    async def inbox_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, InboxReadError):
            status = 504 if exc.issue is DeviceReadIssue.TIMEOUT else 502
            return JSONResponse(status_code=status, content={"detail": str(exc), "issue": exc.issue.value})
        return JSONResponse(
            status_code=503 if isinstance(exc, InboxDisabledError) else 504, content={"detail": str(exc)}
        )

    for error in (InboxReadError, InboxDisabledError, InboxDeadlineError):
        app.add_exception_handler(error, inbox_error)

    async def submission_error(request: Request, exc: Exception) -> JSONResponse:
        code = 422 if isinstance(exc, InvalidSmsError) else 409
        if isinstance(exc, SubmissionNotFoundError):
            code = 404
        elif isinstance(exc, SubmissionDisabledError):
            code = 503
        elif isinstance(exc, SubmissionDeadlineError):
            code = 504
        return JSONResponse(status_code=code, content={"detail": str(exc)})

    for error in (
        InvalidSmsError,
        SubmissionConflictError,
        SubmissionNotFoundError,
        SubmissionDisabledError,
        SubmissionDeadlineError,
    ):
        app.add_exception_handler(error, submission_error)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "adapter_profile": config.device.adapter}

    return app
