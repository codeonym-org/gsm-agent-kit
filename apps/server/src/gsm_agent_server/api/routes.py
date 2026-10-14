import secrets
from typing import Annotated

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from gsm_agent.application.queries.devices import GetDevice, GetDeviceStatus, ListAdapters, ListDevices
from gsm_agent_core.domain.devices import CellularDeviceId
from mediary.cqrs import QuerySender

from gsm_agent_server.api.schemas import AdapterResponse, DeviceResponse, ErrorResponse, StatusResponse

bearer = HTTPBearer(auto_error=False)


async def authorize(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> None:
    token = request.app.state.settings.api_token
    if token is not None:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), token.get_secret_value().encode()
        ):
            raise HTTPException(401, "Invalid API token", headers={"WWW-Authenticate": "Bearer"})


DeviceIdPath = Annotated[str, Path(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")]
router = APIRouter(
    prefix="/api",
    route_class=DishkaRoute,
    dependencies=[Depends(authorize)],
    responses={401: {"model": ErrorResponse}},
)


@router.get("/adapters", response_model=list[AdapterResponse])
async def adapters(queries: FromDishka[QuerySender]) -> list[AdapterResponse]:
    return [AdapterResponse.from_domain(adapter) for adapter in await queries.send(ListAdapters())]


@router.get("/devices", response_model=list[DeviceResponse], responses={504: {"model": ErrorResponse}})
async def devices(queries: FromDishka[QuerySender]) -> list[DeviceResponse]:
    return [DeviceResponse.from_domain(device) for device in await queries.send(ListDevices())]


@router.get(
    "/devices/{device_id}",
    response_model=DeviceResponse,
    responses={404: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def device(device_id: DeviceIdPath, queries: FromDishka[QuerySender]) -> DeviceResponse:
    return DeviceResponse.from_domain(await queries.send(GetDevice(CellularDeviceId(device_id))))


@router.get(
    "/devices/{device_id}/status",
    response_model=StatusResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def status(device_id: DeviceIdPath, queries: FromDishka[QuerySender]) -> StatusResponse:
    return StatusResponse.from_domain(await queries.send(GetDeviceStatus(CellularDeviceId(device_id))))
