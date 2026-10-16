import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from gsm_agent.application.queries.balance import BalancePolicy, ConsultBalance
from gsm_agent_core.capabilities.balance import BalanceSession
from gsm_agent_core.capabilities.catalog import CARRIER_BALANCE_READ
from gsm_agent_core.domain.balance import (
    BalanceCarrier,
    BalanceIssue,
    BalanceObservation,
    BalanceReadError,
    CreditBalance,
    SmsAllowance,
)
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_server.di.container import build_container
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import BalanceSettings
from gsm_agent_simulated import SimulatedDevice
from gsm_agent_zte_mf833t import ZteMf833tDevice, ZteMf833tSettings
from mediary.cqrs import Command, Query, QuerySender
from pydantic import SecretStr, ValidationError

from .test_devices_api import TestDevicesProvider, TestSettings


class FixtureSession:
    def __init__(self) -> None:
        self.calls: list[BalanceCarrier] = []
        self.closes = 0
        self.stage: str | None = None
        self.entered = asyncio.Event()
        self.releasing = asyncio.Event()
        self.closed = asyncio.Event()
        self.result = BalanceObservation("  Crédit: 12,50 DH\nSMS restants: non indiqué  ", datetime.now(UTC))

    async def consult(self, carrier: BalanceCarrier) -> BalanceObservation:
        self.calls.append(carrier)
        self.entered.set()
        if self.stage in ("response", "response_and_cleanup"):
            await asyncio.Event().wait()
        if self.stage == "malformed":
            raise ValueError("private raw firmware payload")
        if self.stage == "unavailable":
            raise BalanceReadError(BalanceIssue.UNAVAILABLE)
        return self.result

    async def close(self) -> None:
        self.closes += 1
        self.releasing.set()
        try:
            if self.stage in ("cleanup", "response_and_cleanup"):
                await asyncio.Event().wait()
            await asyncio.sleep(0)
        finally:
            self.closed.set()


class FixtureDevice(SimulatedDevice):
    def __init__(self, *, stage: str | None = None) -> None:
        super().__init__(CellularDeviceId("balance-device"), balance_enabled=True)
        self.session = FixtureSession()
        self.session.stage = stage
        self.stage = stage
        self.reserved = asyncio.Event()
        self.reserve_cancelled = False

    async def reserve(self) -> BalanceSession:
        self.reserved.set()
        if self.stage == "foreign":
            raise BalanceReadError(BalanceIssue.BUSY)
        if self.stage == "ownership":
            try:
                await asyncio.Event().wait()
            finally:
                self.reserve_cancelled = True
        return self.session


@asynccontextmanager
async def client_for(
    device: SimulatedDevice | ZteMf833tDevice,
    *,
    carrier: BalanceCarrier | None = BalanceCarrier.INWI,
    token: str | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        TestSettings(
            balance=BalanceSettings(carrier=carrier, timeout_seconds=0.02, cleanup_timeout_seconds=0.02),
            api_token=SecretStr(token) if token else None,
        ),
        TestDevicesProvider(device),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as client:
            yield client


async def test_balance_is_a_query_with_raw_text_time_and_unknown_allowances():
    device = FixtureDevice()
    async with client_for(device) as api:
        response = await api.get("/api/devices/balance-device/balance")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        result = response.json()
        assert result["raw_text"] == device.session.result.raw_text
        assert datetime.fromisoformat(result["observed_at"]).utcoffset() is not None
        assert result["credit"] is None and result["sms_allowance"] is None
        assert device.session.calls == [BalanceCarrier.INWI]
        assert device.session.closes == 1
        schema = (await api.get("/openapi.json")).json()["paths"]["/api/devices/{device_id}/balance"]
        assert set(schema) == {"get"}
        assert set(schema["get"]["responses"]) >= {"200", "401", "404", "409", "501", "502", "503", "504"}
        assert "requestBody" not in schema["get"]
    assert issubclass(ConsultBalance, Query) and not issubclass(ConsultBalance, Command)
    assert device.closed


async def test_parsed_credit_and_allowance_are_independent_and_explicit():
    device = FixtureDevice()
    device.session.result = BalanceObservation(
        "Fictional credit 2.50 MAD; 17 SMS for national destinations",
        datetime.now(UTC),
        CreditBalance(Decimal("2.50"), "MAD", "fictional validity"),
        SmsAllowance(17, "national destinations"),
    )
    async with client_for(device) as api:
        result = (await api.get("/api/devices/balance-device/balance")).json()
        assert result["credit"] == {"amount": "2.50", "currency": "MAD", "conditions": "fictional validity"}
        assert result["sms_allowance"] == {"remaining": 17, "conditions": "national destinations"}


@pytest.mark.parametrize(
    "stage,code,issue",
    [
        ("foreign", 409, "busy"),
        ("malformed", 502, "invalid_response"),
        ("unavailable", 503, "unavailable"),
        ("cleanup", 502, "cleanup_failed"),
        ("ownership", 504, None),
        ("response", 504, None),
        ("response_and_cleanup", 504, None),
    ],
)
async def test_failure_deadlines_and_owned_cleanup(stage, code, issue):
    device = FixtureDevice(stage=stage)
    async with client_for(device) as api:
        async with asyncio.timeout(2):
            response = await api.get("/api/devices/balance-device/balance")
        assert response.status_code == code
        assert response.json().get("issue") == issue
        assert "private" not in response.text
        assert device.session.closes == (0 if stage in ("foreign", "ownership") else 1)
        if stage == "ownership":
            assert device.reserve_cancelled and not device.session.calls
        if stage == "foreign":
            assert not device.session.calls
        if stage == "cleanup":
            assert device.session.closed.is_set()


async def test_unsupported_and_unknown_return_without_ownership_or_zte_network_io():
    requests = []

    def forbidden(request):
        requests.append(request)
        raise AssertionError("Unsupported balance must not access hardware")

    zte = ZteMf833tDevice(
        CellularDeviceId("zte"), ZteMf833tSettings(), transport=httpx.MockTransport(forbidden)
    )
    async with client_for(zte, carrier=None) as api:
        response = await api.get("/api/devices/zte/balance")
        assert response.status_code == 501
        assert response.json()["capability"] == "carrier.balance.read"
        assert (await api.get("/api/devices/missing/balance")).status_code == 404
        assert (await api.get("/api/devices/bad%20id/balance")).status_code == 422
        assert not requests
        assert CARRIER_BALANCE_READ.id not in zte.manifest.capabilities
    assert zte.get(CARRIER_BALANCE_READ) is None


async def test_missing_carrier_and_auth_fail_before_reservation():
    device = FixtureDevice()
    async with client_for(device, carrier=None, token="fictional") as api:
        url = "/api/devices/balance-device/balance"
        assert (await api.get(url)).status_code == 401
        result = await api.get(url, headers={"Authorization": "Bearer fictional"})
        assert result.status_code == 503
        assert "GSM_BALANCE__CARRIER" in result.json()["detail"]
        assert not device.reserved.is_set()


@pytest.mark.parametrize("stage", ["response", "ownership", "cleanup"])
async def test_client_cancellation_finishes_only_owned_cleanup(stage):
    device = FixtureDevice(stage=stage)
    container = build_container(
        TestSettings(balance=BalanceSettings(carrier=BalanceCarrier.INWI, cleanup_timeout_seconds=0.01)),
        TestDevicesProvider(device),
    )
    try:
        async with container() as scope:
            sender = await scope.get(QuerySender)
            task = asyncio.create_task(sender.send(ConsultBalance(device.device_id)))
            entered = {
                "response": device.session.entered,
                "ownership": device.reserved,
                "cleanup": device.session.releasing,
            }[stage]
            async with asyncio.timeout(2):
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert device.session.closes == (0 if stage == "ownership" else 1)
            if stage != "ownership":
                assert device.session.closed.is_set()
    finally:
        await container.close()


async def test_simulated_profile_requires_explicit_capability_and_simulated_carrier(monkeypatch):
    monkeypatch.setenv("GSM_DEVICE__SIMULATED_BALANCE_ENABLED", "true")
    monkeypatch.setenv("GSM_BALANCE__CARRIER", "simulated")
    app = create_app(TestSettings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            for _ in range(2):
                response = await api.get("/api/devices/demo-device/balance")
                assert response.status_code == 200 and "SIMULATED" in response.json()["raw_text"]
                assert response.json()["credit"] is None and response.json()["sms_allowance"] is None
            manifest = (await api.get("/api/adapters")).json()[0]
            assert "carrier.balance.read" in manifest["capabilities"]
    device = SimulatedDevice(CellularDeviceId("sim"), balance_enabled=True)
    async with client_for(device) as api:
        assert (await api.get("/api/devices/sim/balance")).status_code == 503
    async with client_for(SimulatedDevice(CellularDeviceId("sim"))) as api:
        assert (await api.get("/api/devices/sim/balance")).status_code == 501


@pytest.mark.parametrize("value", ["*120#", "*120*1#", "unknown"])
def test_configuration_rejects_arbitrary_codes_and_unknown_policies(value):
    with pytest.raises(ValidationError):
        BalanceSettings(carrier=value)


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_budgets_fail_before_device_access(value):
    with pytest.raises(ValueError):
        BalancePolicy(timeout_seconds=value)
    with pytest.raises(ValueError):
        BalancePolicy(cleanup_timeout_seconds=value)
    with pytest.raises(ValidationError):
        BalanceSettings(timeout_seconds=value)
