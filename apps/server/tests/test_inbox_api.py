import asyncio

import httpx
import pytest
from gsm_agent.application.commands.ingest_inbox import IngestInbox
from gsm_agent.application.inbox import InboxDisabledError
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import DeviceSettings, InboxSettings
from gsm_agent_zte_mf833t import ZteMf833tDevice
from mediary.cqrs import CommandSender
from pydantic import SecretStr

from .test_devices_api import TestSettings


def message(slot="1", text="Fictional SMS", complete="1"):
    return {
        "id": slot,
        "number": "+212600000000",
        "date": f"26;01;01;12;00;{int(slot):02};+00",
        "content": text.encode("utf-16-be").hex(),
        "tag": "1",
        "received_all_concat_sms": complete,
    }


def fake_zte(monkeypatch, rows):
    requests = []
    original = ZteMf833tDevice.__init__

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text="DEVICE: 'datacard/mf833T'")
        if request.url.params["cmd"] == "sms_page_data":
            return httpx.Response(200, json={"messages": list(rows)})
        return httpx.Response(
            200, json={"network_provider": "Fictional", "network_type": "LTE", "signalbar": "4"}
        )

    def init(self, device_id, settings, **kwargs):
        original(self, device_id, settings, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(ZteMf833tDevice, "__init__", init)
    return requests


async def wait_for_records(api, count, headers=None):
    async with asyncio.timeout(3):
        while True:
            response = await api.get("/api/devices/zte/messages", headers=headers)
            assert response.status_code == 200
            if len(response.json()) == count:
                return response.json()
            await asyncio.sleep(0.005)


async def test_polling_zte_to_sqlite_api_baselines_then_ingests_and_survives_restart(tmp_path, monkeypatch):
    rows = [message(), message("2", text="old partial", complete="0")]
    requests = fake_zte(monkeypatch, rows)
    settings = TestSettings(
        device=DeviceSettings(adapter="zte-mf833t", id="zte"),
        inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db", poll_interval_seconds=0.02),
        api_token=SecretStr("fictional-token"),
    )
    headers = {"Authorization": "Bearer fictional-token"}
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            assert (await api.get("/api/devices/zte/messages")).status_code == 401
            assert (await api.post("/api/devices/zte/inbox/ingest")).status_code == 401
            initial = await wait_for_records(api, 2, headers)
            assert all(record["baselined"] and not record["replyable"] for record in initial)
            original_id = next(record["id"] for record in initial if record["provider_id"] == "2")
            rows[1] = message("2", text="old partial finished")
            rows.append(message("3", text="new inbound"))
            records = await wait_for_records(api, 3, headers)
            old_partial = next(record for record in records if record["id"] == original_id)
            assert old_partial["complete"] and old_partial["baselined"] and not old_partial["replyable"]
            fresh = next(record for record in records if record["provider_id"] == "3")
            assert fresh["replyable"] and fresh["body"] == "new inbound"
            response = await api.get("/api/devices/zte/messages?limit=1&offset=1", headers=headers)
            assert len(response.json()) == 1
            assert (await api.get("/api/devices/zte/messages?limit=0", headers=headers)).status_code == 422
            assert (await api.get("/api/devices/missing/messages", headers=headers)).status_code == 404
            schema = (await api.get("/openapi.json")).json()["paths"]
            assert set(schema["/api/devices/{device_id}/messages"]) == {"get"}
            assert set(schema["/api/devices/{device_id}/inbox/ingest"]) == {"post"}
    assert all(request.method == "GET" for request in requests)
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(restarted), base_url="http://api.invalid"
        ) as api:
            records = await wait_for_records(api, 3, headers)
            assert fresh["id"] in {record["id"] for record in records}
            response = await api.post("/api/devices/zte/inbox/ingest", headers=headers)
            assert response.status_code == 200
            assert response.json()["queued"] == 0
            assert not response.json()["baselined"]


async def test_disabled_inbox_returns_explicit_error_without_creating_database(tmp_path):
    path = tmp_path / "should-not-exist.db"
    app = create_app(TestSettings(inbox=InboxSettings(database_path=path)))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            assert (await api.get("/api/devices/demo-device/messages")).status_code == 503
            assert (await api.post("/api/devices/demo-device/inbox/ingest")).status_code == 503
    assert not path.exists()


async def test_status_only_adapter_fast_unsupported_inbox(tmp_path):
    app = create_app(TestSettings(inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db")))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            response = await api.post("/api/devices/demo-device/inbox/ingest")
            assert response.status_code == 501
            assert response.json()["capability"] == "sms.inbox.read"


async def test_mediary_keeps_ingestion_a_command_and_disabled_store_explicit(tmp_path):
    from gsm_agent_server.di.container import build_container

    container = build_container(TestSettings())
    try:
        with pytest.raises(InboxDisabledError):
            await container.get(InboxStore)
        async with container() as scope:
            sender = await scope.get(CommandSender)
            with pytest.raises(InboxDisabledError):
                await sender.send(IngestInbox(CellularDeviceId("demo-device")))
    finally:
        await container.close()
