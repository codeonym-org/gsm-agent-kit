"""Authenticated internal feed consumed by the tRPC gateway, never a command API."""

import asyncio
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from gsm_agent_server.infra.realtime import ChangeFeed

router = APIRouter()


@router.websocket("/api/events")
async def changes(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        # Token is carried in the first frame, never in URLs/access logs.
        async with asyncio.timeout(5):
            frame = await websocket.receive_json()
        token = websocket.app.state.settings.api_token
        supplied = frame.get("token", "") if isinstance(frame, dict) else ""
        if not isinstance(supplied, str) or (
            token is not None
            and not secrets.compare_digest(supplied.encode(), token.get_secret_value().encode())
        ):
            await websocket.close(code=4401)
            return
        feed = await websocket.app.state.dishka_container.get(ChangeFeed)
        with feed.subscribe() as queue:
            # Receive concurrently so an idle disconnected client releases its queue.
            receiver = asyncio.create_task(websocket.receive())
            try:
                while not receiver.done():
                    next_change = asyncio.create_task(queue.get())
                    try:
                        ready, _ = await asyncio.wait(
                            (receiver, next_change), timeout=20, return_when=asyncio.FIRST_COMPLETED
                        )
                        if receiver in ready:
                            break
                        await websocket.send_json(
                            {"type": "invalidate", "revision": next_change.result()}
                            if next_change in ready
                            else {"type": "heartbeat"}
                        )
                    finally:
                        next_change.cancel()
                        await asyncio.gather(next_change, return_exceptions=True)
            finally:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
    except WebSocketDisconnect:
        return
    except (TimeoutError, ValueError):
        await websocket.close(code=4400)
