import asyncio

import pytest
from fastapi.testclient import TestClient
from gsm_agent_server.infra.realtime import ChangeFeed
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import Settings
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from starlette.websockets import WebSocketDisconnect


class IsolatedSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="GSM_REALTIME_TEST_")


def test_feed_authenticates_before_streaming_and_releases_on_disconnect() -> None:
    app = create_app(IsolatedSettings(api_token=SecretStr("test-token")))
    with TestClient(app) as client:
        with client.websocket_connect("/api/events") as socket:
            socket.send_json({"token": "wrong"})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4401
        with client.websocket_connect("/api/events") as socket:
            socket.send_json({"token": "test-token"})
            assert socket.receive_json() == {"type": "invalidate", "revision": 0}
            assert client.portal is not None
            feed = client.portal.call(app.state.dishka_container.get, ChangeFeed)
            client.portal.call(feed.publish)
            assert socket.receive_json() == {"type": "invalidate", "revision": 1}
            # Close gracefully and await handler completion before TestClient's
            # context exit cancels the ASGI task. Scheduler timing differs across
            # Python versions/OSes; a fixed sleep cannot synchronize this teardown.
            socket.close()

            async def disconnected() -> None:
                async with asyncio.timeout(2):
                    while feed._subscribers:
                        await asyncio.sleep(0)

            client.portal.call(disconnected)
        assert len(feed._subscribers) == 0


async def test_slow_feed_clients_are_bounded_and_reconnect_gets_current_revision() -> None:
    feed = ChangeFeed()
    with feed.subscribe() as queue:
        for _ in range(1000):
            feed.publish()
        assert queue.qsize() == 1
        assert await queue.get() == 1000
    with feed.subscribe() as queue:
        assert await queue.get() == 1000
