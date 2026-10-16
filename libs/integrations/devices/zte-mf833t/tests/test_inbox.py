import asyncio
from typing import assert_type

import httpx
import pytest
from gsm_agent_core.capabilities.catalog import SMS_INBOX_READ
from gsm_agent_core.capabilities.inbox import SmsInbox
from gsm_agent_core.domain.devices import CellularDeviceId, DeviceReadIssue
from gsm_agent_core.domain.sms import InboxReadError, SmsAddressKind
from gsm_agent_zte_mf833t import ZteMf833tDevice, ZteMf833tSettings

from .test_adapter import CONFIG, STATUS


def row(slot="1", body="Hello مرحبا", **changes):
    return {
        "id": slot,
        "number": "+212600000000",
        "date": "26;01;01;12;00;00;+00",
        "content": body.encode("utf-16-be").hex(),
        "tag": "1",
        "received_all_concat_sms": "1",
        **changes,
    }


def make_device(handler, **settings):
    def respond(request):
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text=CONFIG)
        if request.url.params.get("cmd") != "sms_page_data":
            return httpx.Response(200, json=STATUS)
        return handler(request)

    return ZteMf833tDevice(
        CellularDeviceId("fictional-device"),
        ZteMf833tSettings(**settings),
        transport=httpx.MockTransport(respond),
    )


async def test_complete_pagination_preserves_partial_identity_and_never_mutates_device():
    requests = []

    def respond(request):
        requests.append(request)
        page = int(request.url.params["page"])
        pages = [[row(), row("2", received_all_concat_sms="0")], [row("3", tag="2")]]
        return httpx.Response(200, json={"messages": pages[page]})

    device = make_device(respond, page_size=2, storage_generation="db-a", subscription_generation="sim-b")
    try:
        inbox = device.get(SMS_INBOX_READ)
        assert_type(inbox, SmsInbox | None)
        assert inbox is not None
        result = await inbox.scan()
        assert len(result.items) == 2
        assert result.items[0].body == "Hello مرحبا"
        assert result.items[0].sender.kind is SmsAddressKind.INTERNATIONAL
        assert result.items[0].complete and not result.items[1].complete
        assert result.source.storage_generation == "db-a"
        assert result.subscription_generation == "sim-b"
        assert result.finished_at >= result.started_at
        assert len(requests) == 2
        for request in requests:
            assert request.method == "GET"
            assert request.url.path == "/goform/goform_get_cmd_process"
            assert request.url.params["cmd"] == "sms_page_data"
            assert request.url.params["mem_store"] == "1"
            assert request.url.params["tags"] == "10"
    finally:
        await device.close()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"messages": None},
        {"messages": [None]},
        {"result": "failure", "messages": []},
        {"messages": [row(content="xx")]},
        {"messages": [row(content="D800")]},
        {"messages": [row(tag="unknown")]},
        {"messages": [row(received_all_concat_sms="maybe")]},
        {"messages": [row(date="")]},
        {"messages": [row(id=None)]},
    ],
)
async def test_malformed_pages_never_become_empty_success(payload):
    device = make_device(lambda request: httpx.Response(200, json=payload))
    try:
        with pytest.raises(InboxReadError) as error:
            await device.scan()
        assert error.value.issue is DeviceReadIssue.INVALID_RESPONSE
        assert str(error.value) == "Inbox scan failed: invalid_response"
    finally:
        await device.close()


@pytest.mark.parametrize("cycle", [False, True])
async def test_repeated_or_cycling_pages_fail_the_whole_scan(cycle):
    def respond(request):
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"messages": [row(str(page % 2 if cycle else 1))]})

    device = make_device(respond, page_size=1, max_pages=5)
    try:
        with pytest.raises(InboxReadError):
            await device.scan()
    finally:
        await device.close()


@pytest.mark.parametrize("failure", ["offline", "login", "bad-page", "limit", "changed-slot"])
async def test_later_page_failure_discards_earlier_messages(failure):
    def respond(request):
        page = int(request.url.params["page"])
        if page == 0 or failure == "limit":
            return httpx.Response(200, json={"messages": [row(str(page))]})
        if failure == "offline":
            raise httpx.ConnectError("fictional failure", request=request)
        if failure == "login":
            return httpx.Response(200, json={"loginfo": "no"})
        if failure == "changed-slot":
            return httpx.Response(200, json={"messages": [row("0", body="reused")]})
        return httpx.Response(200, json={"messages": "bad"})

    device = make_device(respond, page_size=1, max_pages=2)
    try:
        with pytest.raises(InboxReadError):
            await device.scan()
        assert device.get(SMS_INBOX_READ) is not None
    finally:
        await device.close()


async def test_inbox_deadline_includes_waiting_for_its_lock_and_external_cancellation_propagates():
    device = make_device(
        lambda request: httpx.Response(200, json={"messages": []}), inbox_timeout_seconds=0.02
    )
    try:
        async with device._inbox_lock:
            with pytest.raises(InboxReadError) as exc:
                await device.scan()
            assert exc.value.issue is DeviceReadIssue.TIMEOUT
            task = asyncio.create_task(device.scan())
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    finally:
        await device.close()


async def test_inbox_budget_covers_all_pages():
    async def respond(request):
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"messages": [row(request.url.params["page"])]})

    # MockTransport awaits an async result from the dispatch function.
    device = make_device(respond, page_size=1, inbox_timeout_seconds=0.03)
    try:
        with pytest.raises(InboxReadError) as exc:
            await device.scan()
        assert exc.value.issue is DeviceReadIssue.TIMEOUT
    finally:
        await device.close()


@pytest.mark.parametrize(
    "response,issue",
    [
        (httpx.Response(403), DeviceReadIssue.AUTH_REQUIRED),
        (httpx.Response(302, headers={"Location": "http://other.invalid"}), DeviceReadIssue.AUTH_REQUIRED),
        (httpx.Response(200, text="<html>Login</html>"), DeviceReadIssue.INVALID_RESPONSE),
        (httpx.Response(200, json={"messages": [row(), row()]}), DeviceReadIssue.INVALID_RESPONSE),
    ],
)
async def test_login_redirects_and_duplicate_slots_cannot_form_an_inbox(response, issue):
    device = make_device(lambda request: response)
    try:
        with pytest.raises(InboxReadError) as error:
            await device.scan()
        assert error.value.issue is issue
    finally:
        await device.close()


@pytest.mark.parametrize(
    "settings",
    [
        {"inbox_timeout_seconds": float("nan")},
        {"inbox_timeout_seconds": 0},
        {"page_size": 0},
        {"page_size": 501},
        {"max_pages": 0},
        {"storage_generation": " "},
        {"subscription_generation": ""},
    ],
)
def test_invalid_inbox_configuration_fails_before_device_access(settings):
    with pytest.raises(ValueError):
        ZteMf833tSettings(**settings)
