"""Production Caddy and bundled-gateway checks, inside the fixture network only."""

import asyncio
import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

ORIGIN = "http://console:8080"
SOCKET = "ws://console:8080/trpc?connectionParams=1"


def read(path):
    with urlopen(ORIGIN + path, timeout=5) as response:
        return response.read().decode(), response.headers


async def check_console():
    index, headers = read("/")
    assert "GSM Agent Kit" in index and "no-cache" in headers["Cache-Control"]
    for path in ("/inbox", "/jobs", "/device"):
        assert read(path)[0] == index, "Production host must serve SPA deep links"
    assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', index)
    assert any(asset.endswith(".js") for asset in assets)
    for asset in assets:
        body, headers = read(asset)
        assert "immutable" in headers["Cache-Control"]
        assert "smoke-only-token" not in body
        if asset.endswith(".js"):
            assert "javascript" in headers["Content-Type"]
    assert "MIT" in read("/third-party-notices.txt")[0]

    # Auth failures and backend 404s must stay JSON rather than become index.html.
    for path, token, expected in (
        ("/api/adapters", "", 401),
        ("/api/adapters", "wrong-synthetic-token", 401),
        ("/api/does-not-exist", "smoke-only-token", 404),
    ):
        try:
            with urlopen(Request(ORIGIN + path, headers={"Authorization": "Bearer " + token}), timeout=5):
                raise AssertionError("Proxy unexpectedly accepted the request")
        except HTTPError as error:
            assert error.code == expected and "application/json" in error.headers["Content-Type"]
            assert "<!doctype" not in error.read().decode().lower()

    async with asyncio.timeout(10):
        async with connect(SOCKET, origin=ORIGIN, open_timeout=5, close_timeout=2) as socket:
            await socket.send(
                json.dumps({"method": "connectionParams", "data": {"token": "smoke-only-token"}})
            )
            await socket.send(json.dumps({"id": 1, "method": "subscription", "params": {"path": "changes"}}))
            while True:
                message = json.loads(await socket.recv())
                if message.get("result", {}).get("data", {}).get("state") == "live":
                    break

    async with asyncio.timeout(10):
        async with connect(SOCKET, origin=ORIGIN, open_timeout=5, close_timeout=2) as socket:
            await socket.send(json.dumps({"method": "connectionParams", "data": {"token": "wrong-token"}}))
            while True:
                message = await socket.recv()
                if "UNAUTHORIZED" in str(message):
                    break
    try:
        async with connect(SOCKET, origin="http://foreign.invalid", open_timeout=5):
            raise AssertionError("Cross-origin WebSocket was accepted")
    except InvalidStatus as error:
        assert error.response.status_code == 403
    print("PASS: production SPA/assets, HTTP auth/errors and authenticated same-origin tRPC feed")
