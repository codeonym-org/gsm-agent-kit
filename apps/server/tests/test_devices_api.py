import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import assert_type

import pytest
from dishka import Provider, Scope, provide
from fastapi.testclient import TestClient
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.queries.devices import GetDeviceStatus, ListAdapters, ListDevices
from gsm_agent_core.capabilities.catalog import CapabilityKey
from gsm_agent_core.domain.devices import (
    AdapterManifest,
    Availability,
    CellularDeviceId,
    DeviceDescriptor,
    DeviceModel,
    DeviceStatus,
)
from gsm_agent_core.ports import CellularDevice
from gsm_agent_server.di.container import build_container
from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import DeviceSettings, Settings
from gsm_agent_simulated import MANIFEST, SimulatedDevice
from mediary import Mediator
from mediary.cqrs import Query, QuerySender
from pydantic import SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict


class StatuslessDevice:
    device_id = CellularDeviceId("statusless")
    manifest = AdapterManifest("statusless-test", "0.1.0", DeviceModel("Fictional", "No status"), ())

    async def describe(self) -> DeviceDescriptor:
        return DeviceDescriptor(self.device_id, self.manifest)

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return None

    async def close(self) -> None:
        pass


class StalledDevice(SimulatedDevice):
    cancelled = False

    async def read(self) -> DeviceStatus:
        try:
            await asyncio.sleep(60)
            return DeviceStatus(Availability.UNKNOWN, datetime.now(UTC))
        finally:
            self.cancelled = True


class TestDevicesProvider(Provider):
    __test__ = False
    scope = Scope.APP

    def __init__(self, *devices: CellularDevice) -> None:
        super().__init__()
        self.configured = devices

    @provide(override=True)
    async def devices(self) -> AsyncIterator[DeviceDirectory]:
        manifests = tuple(
            {device.manifest.adapter_id: device.manifest for device in self.configured}.values()
        )
        try:
            yield ConfiguredDevices(self.configured, manifests)
        finally:
            for device in self.configured:
                await device.close()


class TestSettings(Settings):
    __test__ = False
    model_config = SettingsConfigDict(env_file=None)


def settings(**kwargs) -> Settings:
    return TestSettings(**kwargs)


def test_api_exposes_device_identity_adapter_version_and_only_implemented_capabilities() -> None:
    with TestClient(create_app(settings())) as client:
        assert client.get("/health").json() == {"status": "ok", "adapter_profile": "simulated"}
        adapter = client.get("/api/adapters").json()[0]
        assert adapter["adapter_id"] == "simulated"
        assert adapter["version"] == MANIFEST.version
        assert adapter["capabilities"] == ["device.status.read"]
        listing = client.get("/api/devices").json()
        assert listing == [{"device_id": "demo-device", "adapter": adapter}]
        assert client.get("/api/devices/demo-device").json() == listing[0]
        status = client.get("/api/devices/demo-device/status")
        assert status.status_code == 200
        assert status.json()["availability"] == "ready"
        assert datetime.fromisoformat(status.json()["observed_at"]).utcoffset() is not None
        assert status.json()["network_provider"] is None
        schema = client.get("/openapi.json").json()
        assert "post" not in schema["paths"]["/api/devices/{device_id}/status"]
        assert "501" in schema["paths"]["/api/devices/{device_id}/status"]["get"]["responses"]


def test_another_adapter_and_unavailable_status_use_the_same_queries_and_close_on_shutdown() -> None:
    offline = SimulatedDevice(CellularDeviceId("offline"), availability=Availability.UNAVAILABLE)
    other = StatuslessDevice()
    assert_type(other, StatuslessDevice)
    with TestClient(create_app(settings(), TestDevicesProvider(offline, other))) as client:
        assert len(client.get("/api/devices").json()) == 2
        assert client.get("/api/devices/offline/status").json()["availability"] == "unavailable"
        assert client.get("/api/devices/offline").json()["adapter"]["capabilities"] == ["device.status.read"]
        unsupported = client.get("/api/devices/statusless/status")
        assert unsupported.status_code == 501
        assert unsupported.json()["capability"] == "device.status.read"
        assert client.get("/api/devices/statusless").json()["adapter"]["capabilities"] == []
        assert not offline.closed
    assert offline.closed


def test_unknown_identity_and_invalid_path_are_explicit_errors() -> None:
    with TestClient(create_app(settings())) as client:
        assert client.get("/api/devices/absent").status_code == 404
        assert client.get("/api/devices/absent/status").status_code == 404
        assert client.get("/api/devices/invalid%20id").status_code == 422


def test_api_token_and_settings_are_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GSM_DEVICE__ID", "configured")
    monkeypatch.setenv("GSM_DEVICE__SIMULATED_AVAILABILITY", "busy")
    config = settings(api_token=SecretStr("fictional-test-token"))
    with TestClient(create_app(config)) as client:
        assert client.get("/api/devices").status_code == 401
        assert client.get("/api/devices", headers={"Authorization": "Bearer wrong"}).status_code == 401
        response = client.get(
            "/api/devices/configured/status", headers={"Authorization": "Bearer fictional-test-token"}
        )
        assert response.status_code == 200
        assert response.json()["availability"] == "busy"


def test_query_deadline_cancels_the_operation_and_retains_support() -> None:
    device = StalledDevice(CellularDeviceId("stalled"))
    config = settings(query_timeout_seconds=0.01)
    with TestClient(create_app(config, TestDevicesProvider(device))) as client:
        response = client.get("/api/devices/stalled/status")
        assert response.status_code == 504
        assert device.cancelled
        assert client.get("/api/devices/stalled").json()["adapter"]["capabilities"] == ["device.status.read"]
    assert device.closed


def test_duplicate_ids_fail_startup_and_cleanup_devices() -> None:
    one = SimulatedDevice(CellularDeviceId("duplicate"))
    two = SimulatedDevice(CellularDeviceId("duplicate"))
    with pytest.raises(ValueError, match="Duplicate logical"):
        with TestClient(create_app(settings(), TestDevicesProvider(one, two))):
            pass
    assert one.closed and two.closed


async def test_mediary_dispatches_only_query_contracts_with_typed_results() -> None:
    container = build_container(settings())
    try:
        async with container() as scope:
            queries = await scope.get(QuerySender)
            mediator = await scope.get(Mediator)
            assert all(issubclass(item.message_type, Query) for item in mediator.registrations().handlers)
            assert len(await queries.send(ListAdapters())) == 1
            assert len(await queries.send(ListDevices())) == 1
            result = await queries.send(GetDeviceStatus(CellularDeviceId("demo-device")))
            assert_type(result, DeviceStatus)
            assert result.availability is Availability.READY
    finally:
        await container.close()


def test_invalid_configuration_is_rejected_before_device_io() -> None:
    with pytest.raises(ValidationError):
        settings(device=DeviceSettings(id="bad id"))
    with pytest.raises(ValidationError):
        settings(query_timeout_seconds=float("nan"))
    with pytest.raises(ValidationError):
        settings(device={"adapter": "unknown"})
