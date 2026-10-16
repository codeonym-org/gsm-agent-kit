import asyncio
from dataclasses import replace
from typing import assert_type

import httpx
import pytest
from gsm_agent_core.capabilities.catalog import DEVICE_STATUS_READ
from gsm_agent_core.capabilities.status import DeviceStatusReader
from gsm_agent_core.domain.devices import (
    Availability,
    CellularDeviceId,
    Compatibility,
    DeviceReadIssue,
    VerificationKind,
)
from gsm_agent_core.ports import CellularDevice
from gsm_agent_zte_mf833t import MANIFEST, ZteMf833tDevice, ZteMf833tSettings
from gsm_agent_zte_mf833t import adapter as adapter_module

CONFIG = "define(function() { return { DEVICE: 'datacard/mf833T' }; });"
STATUS = {
    "wa_inner_version": "BD_WANAMARMF833TV1.0.0B04",
    "hardware_version": "djtA",
    "network_provider": "Fictional carrier",
    "network_type": "LTE",
    "signalbar": "4",
}


def make_device(handler, *, timeout: float = 1) -> ZteMf833tDevice:
    return ZteMf833tDevice(
        CellularDeviceId("fictional-device"),
        ZteMf833tSettings("http://device.invalid", timeout),
        transport=httpx.MockTransport(handler),
    )


async def test_read_only_normalization_and_typed_capability_contract() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text=CONFIG)
        return httpx.Response(200, json=STATUS)

    device: CellularDevice = make_device(respond)
    try:
        descriptor = await device.describe()
        assert descriptor.adapter.adapter_id == "zte-mf833t"
        assert descriptor.adapter.version == MANIFEST.version
        assert descriptor.observation is not None
        assert descriptor.observation.observed_model == "MF833T"
        assert descriptor.observation.compatibility is Compatibility.VERIFIED
        assert descriptor.observation.variant is not None
        assert descriptor.observation.variant.firmware == STATUS["wa_inner_version"]
        reader = device.get(DEVICE_STATUS_READ)
        assert_type(reader, DeviceStatusReader | None)
        assert reader is not None
        status = await reader.read()
        assert status.availability is Availability.READY
        assert status.network_provider == "Fictional carrier"
        assert status.network_type == "LTE"
        assert status.signal_percent == 80
        assert status.issue is None
        assert all(request.method == "GET" for request in requests)
        for request in requests:
            assert request.headers["Referer"] == "http://device.invalid/index.html"
            if request.url.path.endswith("goform_get_cmd_process"):
                assert set(request.url.params["cmd"].split(",")) == set(STATUS)
                assert request.url.params["multi_data"] == "1"
    finally:
        await device.close()


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({**STATUS, "wa_inner_version": "fictional-new-firmware"}, Compatibility.UNTESTED),
        ({**STATUS, "hardware_version": "fictional-new-revision"}, Compatibility.UNTESTED),
        ({**STATUS, "wa_inner_version": ""}, Compatibility.UNKNOWN),
    ],
)
async def test_variant_matching_does_not_infer_compatibility_from_model(payload, expected) -> None:
    device = make_device(
        lambda request: (
            httpx.Response(200, text=CONFIG)
            if request.url.path.endswith("config.js")
            else httpx.Response(200, json=payload)
        )
    )
    try:
        observation = (await device.describe()).observation
        assert observation is not None
        assert observation.compatibility is expected
        assert observation.availability is Availability.READY
    finally:
        await device.close()


@pytest.mark.parametrize(
    "kind,capabilities",
    [
        (VerificationKind.PROTOCOL_FIXTURE, (DEVICE_STATUS_READ.id,)),
        (VerificationKind.DEVICE_VERIFICATION, ()),
    ],
)
async def test_verification_requires_device_evidence_for_every_declared_capability(
    monkeypatch, kind, capabilities
) -> None:
    evidence = replace(MANIFEST.compatibility_evidence[0], kind=kind, capabilities=capabilities)
    monkeypatch.setattr(adapter_module, "MANIFEST", replace(MANIFEST, compatibility_evidence=(evidence,)))
    device = make_device(
        lambda request: (
            httpx.Response(200, text=CONFIG)
            if request.url.path.endswith("config.js")
            else httpx.Response(200, json=STATUS)
        )
    )
    try:
        observation = (await device.describe()).observation
        assert observation is not None
        assert observation.compatibility is Compatibility.UNTESTED
    finally:
        await device.close()


@pytest.mark.parametrize(
    "config,issue,compatibility",
    [
        ("DEVICE: 'datacard/MF999'", DeviceReadIssue.MODEL_MISMATCH, Compatibility.MISMATCH),
        ("<html>Login</html>", DeviceReadIssue.IDENTITY_UNKNOWN, Compatibility.UNKNOWN),
    ],
)
async def test_unknown_or_wrong_model_never_produces_ready_status(config, issue, compatibility) -> None:
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=config)

    device = make_device(respond)
    try:
        descriptor = await device.describe()
        assert descriptor.observation is not None
        assert descriptor.observation.issue is issue
        assert descriptor.observation.compatibility is compatibility
        assert descriptor.observation.availability is not Availability.READY
        assert len(requests) == 1  # A different model's goform API is never probed.
        assert device.get(DEVICE_STATUS_READ) is not None
    finally:
        await device.close()


@pytest.mark.parametrize(
    "response,issue,availability",
    [
        (httpx.Response(200, json=[]), DeviceReadIssue.INVALID_RESPONSE, Availability.UNKNOWN),
        (httpx.Response(200, json={}), DeviceReadIssue.INVALID_RESPONSE, Availability.UNKNOWN),
        (
            httpx.Response(200, text="<html>Login</html>"),
            DeviceReadIssue.INVALID_RESPONSE,
            Availability.UNKNOWN,
        ),
        (
            httpx.Response(200, json={"loginfo": "no"}),
            DeviceReadIssue.AUTH_REQUIRED,
            Availability.UNAVAILABLE,
        ),
        (httpx.Response(403), DeviceReadIssue.AUTH_REQUIRED, Availability.UNAVAILABLE),
        (
            httpx.Response(302, headers={"Location": "http://other.invalid"}),
            DeviceReadIssue.AUTH_REQUIRED,
            Availability.UNAVAILABLE,
        ),
        (
            httpx.Response(200, json={**STATUS, "signalbar": "9"}),
            DeviceReadIssue.INVALID_RESPONSE,
            Availability.UNKNOWN,
        ),
        (
            httpx.Response(200, json={**STATUS, "signalbar": True}),
            DeviceReadIssue.INVALID_RESPONSE,
            Availability.UNKNOWN,
        ),
        (
            httpx.Response(200, json={**STATUS, "network_type": {}}),
            DeviceReadIssue.INVALID_RESPONSE,
            Availability.UNKNOWN,
        ),
        (
            httpx.Response(200, json={"wa_inner_version": "example"}),
            DeviceReadIssue.INVALID_RESPONSE,
            Availability.UNKNOWN,
        ),
    ],
)
async def test_bad_payloads_and_login_never_become_successful_empty_status(response, issue, availability):
    device = make_device(
        lambda request: (
            httpx.Response(200, text=CONFIG) if request.url.path.endswith("config.js") else response
        )
    )
    try:
        status = await device.read()
        assert status.issue is issue
        assert status.availability is availability
        assert status.network_provider is None
        assert status.network_type is None
        assert status.signal_percent is None
    finally:
        await device.close()


@pytest.mark.parametrize(
    "error,issue",
    [(httpx.ConnectError, DeviceReadIssue.OFFLINE), (httpx.ReadTimeout, DeviceReadIssue.TIMEOUT)],
)
async def test_transport_failure_retains_capability_without_stale_observations(error, issue) -> None:
    fail = False

    def respond(request):
        if fail:
            raise error("fictional network failure", request=request)
        return (
            httpx.Response(200, text=CONFIG)
            if request.url.path.endswith("config.js")
            else httpx.Response(200, json=STATUS)
        )

    device = make_device(respond)
    try:
        assert (await device.read()).availability is Availability.READY
        fail = True
        descriptor = await device.describe()
        assert descriptor.observation is not None
        assert descriptor.observation.variant is None
        assert descriptor.observation.compatibility is Compatibility.UNKNOWN
        assert descriptor.observation.issue is issue
        assert device.get(DEVICE_STATUS_READ) is not None
        status = await device.read()
        assert status.availability is Availability.UNAVAILABLE
        assert status.signal_percent is None
    finally:
        await device.close()


async def test_total_budget_covers_both_requests_even_when_transport_does_not_enforce_httpx_timeout() -> None:
    async def respond(request):
        await asyncio.sleep(0.03)
        return (
            httpx.Response(200, text=CONFIG)
            if request.url.path.endswith("config.js")
            else httpx.Response(200, json=STATUS)
        )

    device = make_device(respond, timeout=0.05)
    try:
        status = await device.read()
        assert status.issue is DeviceReadIssue.TIMEOUT
        assert status.availability is Availability.UNAVAILABLE
    finally:
        await device.close()


async def test_external_cancellation_is_not_converted_into_an_observation_and_close_releases_transport():
    entered = asyncio.Event()

    class BlockingTransport(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            entered.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        async def aclose(self) -> None:
            self.closed = True

    transport = BlockingTransport()
    device = ZteMf833tDevice(CellularDeviceId("cancelled"), ZteMf833tSettings(), transport=transport)
    task = asyncio.create_task(device.read())
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await device.close()
    assert transport.closed
    with pytest.raises(RuntimeError, match="closed"):
        await device.read()


@pytest.mark.parametrize(
    "url", ["file:///tmp/device", "http://user:password@example.invalid", "http://device/x"]
)
def test_invalid_connection_settings_are_rejected_before_io(url):
    with pytest.raises(ValueError):
        ZteMf833tSettings(url)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_time_budget_is_rejected(timeout):
    with pytest.raises(ValueError):
        ZteMf833tSettings(timeout_seconds=timeout)
