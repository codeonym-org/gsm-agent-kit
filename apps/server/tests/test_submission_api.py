from urllib.parse import parse_qs
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import DeviceSettings, SubmissionSettings, ZteHttpSettings
from gsm_agent_zte_mf833t import ZteMf833tDevice
from pydantic import SecretStr

from .test_devices_api import TestSettings


def fake_sender(monkeypatch, path, *, outcome="3"):
    posts = []
    requests = []
    original = ZteMf833tDevice.__init__

    async def respond(request):
        requests.append(request)
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text="DEVICE: 'datacard/mf833T'")
        if request.method == "POST":
            # Observe intent/attempt through an independent connection before device effects.
            async with aiosqlite.connect(path) as connection:
                async with connection.execute(
                    "SELECT COUNT(*) FROM sms_attempts WHERE outcome IS NULL"
                ) as cursor:
                    row = await cursor.fetchone()
                    assert row is not None and row[0] == 1
            posts.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"result": "success"})
        if request.url.params["cmd"] == "sms_cmd_status_info":
            return httpx.Response(200, json={"sms_cmd_status_result": outcome})
        return httpx.Response(
            200, json={"network_provider": "Fictional", "network_type": "LTE", "signalbar": "3"}
        )

    def init(self, device_id, settings, **kwargs):
        original(self, device_id, settings, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(ZteMf833tDevice, "__init__", init)
    return posts, requests


def config(path, **kwargs):
    return TestSettings(
        device=DeviceSettings(
            id="zte", adapter="zte-mf833t", zte_mf833t=ZteHttpSettings(send_poll_interval_seconds=0.001)
        ),
        submissions=SubmissionSettings(enabled=True, database_path=path),
        **kwargs,
    )


async def test_api_persists_before_io_normalizes_splits_and_repeated_request_is_idempotent(
    tmp_path, monkeypatch
):
    path = tmp_path / "submissions.db"
    posts, requests = fake_sender(monkeypatch, path)
    settings = config(path, api_token=SecretStr("fictional-token"))
    body = {"request_id": str(uuid4()), "destination": "+212600000000", "text": "**Hello** world. " * 15}
    headers = {"Authorization": "Bearer fictional-token"}
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            assert (await api.post("/api/devices/zte/submissions", json=body)).status_code == 401
            first = await api.post("/api/devices/zte/submissions", json=body, headers=headers)
            assert first.status_code == 200
            result = first.json()
            assert result["complete"] and result["accepted_parts"] == 2 and not result["blocked"]
            assert "request_digest" not in result and "delivered" not in result
            assert all("**" not in part["text"] for part in result["parts"])
            assert len(posts) == 2
            assert all(post["goformId"] == ["SEND_SMS"] for post in posts)
            count = len(requests)
            queried = await api.get(f"/api/devices/zte/submissions/{body['request_id']}", headers=headers)
            assert queried.json() == result and len(requests) == count
            again = await api.post("/api/devices/zte/submissions", json=body, headers=headers)
            assert again.json() == result and len(posts) == 2
            conflict = await api.post(
                "/api/devices/zte/submissions", json={**body, "text": "changed"}, headers=headers
            )
            assert conflict.status_code == 409 and len(posts) == 2
            assert (
                await api.get(f"/api/devices/zte/submissions/{uuid4()}", headers=headers)
            ).status_code == 404
            invalid = await api.post(
                "/api/devices/zte/submissions",
                json={**body, "request_id": str(uuid4()), "text": "😀"},
                headers=headers,
            )
            assert invalid.status_code == 422 and len(posts) == 2
            schema = (await api.get("/openapi.json")).json()["paths"]
            assert set(schema["/api/devices/{device_id}/submissions"]) == {"post"}
            assert set(schema["/api/devices/{device_id}/submissions/{request_id}"]) == {"get"}
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(restarted), base_url="http://api.invalid"
        ) as api:
            assert (
                await api.post("/api/devices/zte/submissions", json=body, headers=headers)
            ).json() == result
            assert len(posts) == 2


async def test_unknown_outcome_returns_durable_progress_and_prevents_resend(tmp_path, monkeypatch):
    path = tmp_path / "submissions.db"
    posts, _ = fake_sender(monkeypatch, path, outcome="missing")
    body = {"request_id": str(uuid4()), "destination": "+212600000000", "text": "Hello"}
    app = create_app(config(path))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            first = await api.post("/api/devices/zte/submissions", json=body)
            assert first.status_code == 200 and first.json()["blocked"]
            assert first.json()["parts"][0]["state"] == "unknown"
            assert (await api.post("/api/devices/zte/submissions", json=body)).json() == first.json()
            assert len(posts) == 1


async def test_disabled_and_unsupported_submission_profiles(tmp_path):
    body = {"request_id": str(uuid4()), "destination": "+212600000000", "text": "Hello"}
    app = create_app(TestSettings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            assert (await api.post("/api/devices/demo-device/submissions", json=body)).status_code == 503
    app = create_app(
        TestSettings(submissions=SubmissionSettings(enabled=True, database_path=tmp_path / "submissions.db"))
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            assert (await api.post("/api/devices/demo-device/submissions", json=body)).status_code == 501
            assert (await api.post("/api/devices/missing/submissions", json=body)).status_code == 404


@pytest.mark.parametrize("destination", ["0612345678", "+0123", "CarrierName", "+212600000000\n"])
async def test_invalid_destination_is_a_validation_error(destination):
    app = create_app(TestSettings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            response = await api.post(
                "/api/devices/demo-device/submissions",
                json={"request_id": str(uuid4()), "destination": destination, "text": "Hello"},
            )
            assert response.status_code == 422
