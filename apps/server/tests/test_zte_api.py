import httpx
import pytest
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import DeviceSettings, ZteHttpSettings
from gsm_agent_zte_mf833t import MANIFEST, ZteMf833tDevice

from .test_devices_api import TestSettings


async def test_configured_zte_profile_uses_the_real_composition_and_query_path(monkeypatch):
    requests: list[httpx.Request] = []
    closed = []
    original_init = ZteMf833tDevice.__init__
    original_close = ZteMf833tDevice.close

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text="DEVICE: 'datacard/mf833T'")
        return httpx.Response(
            200,
            json={
                "wa_inner_version": "fictional-firmware",
                "hardware_version": "fictional-hardware",
                "network_provider": "Fictional carrier",
                "network_type": "LTE",
                "signalbar": "5",
            },
        )

    def init(self, device_id, settings, **kwargs):
        original_init(self, device_id, settings, transport=httpx.MockTransport(respond))

    async def close(self):
        closed.append(self.device_id)
        await original_close(self)

    monkeypatch.setattr(ZteMf833tDevice, "__init__", init)
    monkeypatch.setattr(ZteMf833tDevice, "close", close)
    monkeypatch.setenv("GSM_DEVICE__ADAPTER", "zte-mf833t")
    monkeypatch.setenv("GSM_DEVICE__ID", "zte-device")
    monkeypatch.setenv("GSM_DEVICE__ZTE_MF833T__BASE_URL", "http://fictional.invalid:8080")
    app = create_app(TestSettings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api.invalid"
        ) as api:
            adapters = (await api.get("/api/adapters")).json()
            assert adapters[0]["adapter_id"] == "zte-mf833t"
            assert adapters[0]["version"] == MANIFEST.version
            assert adapters[0]["capabilities"] == ["device.status.read", "sms.inbox.read", "sms.send"]
            assert adapters[0]["required_transports"] == ["http-management"]
            descriptor = (await api.get("/api/devices/zte-device")).json()
            assert descriptor["observation"]["variant"]["firmware"] == "fictional-firmware"
            assert descriptor["observation"]["compatibility"] == "untested"
            status = (await api.get("/api/devices/zte-device/status")).json()
            assert status["signal_percent"] == 100
            assert status["network_type"] == "LTE"
            assert all(r.url.host == "fictional.invalid" and r.url.port == 8080 for r in requests)
    assert len(closed) == 1


async def test_invalid_zte_origin_fails_startup_without_network_access():
    config = TestSettings(
        device=DeviceSettings(adapter="zte-mf833t", zte_mf833t=ZteHttpSettings(base_url="file:///tmp"))
    )
    app = create_app(config)
    with pytest.raises(ValueError, match="origin"):
        async with app.router.lifespan_context(app):
            pass
