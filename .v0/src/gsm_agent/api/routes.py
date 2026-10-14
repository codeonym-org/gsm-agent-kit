import secrets
from dataclasses import asdict
from typing import Annotated

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from mediary import Mediator
from mediary.cqrs import CommandSender, QuerySender
from pydantic import TypeAdapter

from gsm_agent.api.schemas import AgentBody, SendSmsBody
from gsm_agent.application.commands.send_sms import SendSms
from gsm_agent.application.queries.agent import InvokeAgent, StreamAgent
from gsm_agent.application.queries.balance import ConsultBalance
from gsm_agent.application.queries.messages import GetModemStatus, ListMessages
from gsm_agent.domain.agent import AgentStreamEvent
from gsm_agent.runtime.settings import Settings


async def authorize(request: Request) -> None:
    settings: Settings = request.app.state.settings
    if settings.api_token:
        expected = "Bearer " + settings.api_token.get_secret_value()
        if not secrets.compare_digest(request.headers.get("authorization", ""), expected):
            raise HTTPException(401, "Invalid API token")


router = APIRouter(prefix="/api", route_class=DishkaRoute, dependencies=[Depends(authorize)])


@router.get("/modem/status")
async def modem_status(queries: FromDishka[QuerySender]):
    return asdict(await queries.send(GetModemStatus()))


@router.get("/modem/balance")
@router.post("/modem/balance", include_in_schema=False)
async def modem_balance(queries: FromDishka[QuerySender]):
    """Start one carrier USSD balance consultation using the configured code."""
    return asdict(await queries.send(ConsultBalance()))


@router.get("/messages")
async def messages(queries: FromDishka[QuerySender], limit: Annotated[int, Query(ge=1, le=200)] = 50):
    records = await queries.send(ListMessages(limit))
    return [{"key": r.message.key, **asdict(r)} for r in records]


@router.post("/sms")
async def send_sms(body: SendSmsBody, commands: FromDishka[CommandSender]):
    return asdict(await commands.send(SendSms(body.recipient, body.text)))


@router.post("/agent/invoke")
async def invoke_agent(body: AgentBody, queries: FromDishka[QuerySender]):
    return asdict(await queries.send(InvokeAgent(body.to_input())))


@router.post("/agent/stream")
async def stream_agent(body: AgentBody, mediator: FromDishka[Mediator]):
    request = body.to_input()

    async def events():
        adapter = TypeAdapter(AgentStreamEvent)
        try:
            async with mediator.stream(StreamAgent(request)) as stream:
                async for event in stream:
                    yield f"event: {event.kind}\ndata: {adapter.dump_json(event).decode()}\n\n"
        except Exception:
            # The headers may already be sent; errors travel through the SSE stream.
            yield 'event: error\ndata: {"detail":"Agent stream failed"}\n\n'

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
