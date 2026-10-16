import asyncio
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest
from gsm_agent_core.capabilities.catalog import SMS_SEND
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import (
    PreparedSms,
    SmsDestination,
    SmsEncoding,
    SubmissionOutcome,
    SubmissionReason,
)
from gsm_agent_zte_mf833t import ZteMf833tDevice, ZteMf833tSettings

from .test_adapter import CONFIG, STATUS

SMS = PreparedSms("message-one", "attempt-one", SmsDestination("+212600000000"), "Hello", SmsEncoding.GSM7)


def device_with(handler, **settings):
    async def respond(request):
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text=CONFIG)
        if request.url.params.get("cmd") not in ("sms_cmd_status_info", None):
            return httpx.Response(200, json=STATUS)
        result = handler(request)
        return await result if asyncio.iscoroutine(result) else result

    return ZteMf833tDevice(
        CellularDeviceId("fictional-device"),
        ZteMf833tSettings(send_poll_interval_seconds=0.001, **settings),
        transport=httpx.MockTransport(respond),
    )


async def submit(device, sms=SMS):
    sender = device.get(SMS_SEND)
    assert sender is not None
    return await sender.submit(sms)


async def test_post_ack_is_followed_by_completion_and_wire_values_are_adapter_owned():
    requests = []
    statuses = iter(["1", "3"])

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"result": "success"}
            if request.method == "POST"
            else {"sms_cmd_status_result": next(statuses)},
        )

    device = device_with(respond)
    try:
        result = await submit(device)
        assert result.outcome is SubmissionOutcome.ACCEPTED
        assert result.message_id == SMS.message_id and result.attempt_id == SMS.attempt_id
        assert [request.method for request in requests] == ["POST", "GET", "GET"]
        form = parse_qs(requests[0].content.decode())
        assert form["goformId"] == ["SEND_SMS"] and form["Number"] == [SMS.destination.value]
        assert bytes.fromhex(form["MessageBody"][0]).decode("utf-16-be") == SMS.text
        assert form["encode_type"] == ["GSM7_default"]
        assert all(request.url.params["sms_cmd"] == "4" for request in requests[1:])
    finally:
        await device.close()


@pytest.mark.parametrize(
    "ack,status,outcome",
    [
        ({"result": "failure"}, None, SubmissionOutcome.REJECTED),
        ({"result": "success"}, "2", SubmissionOutcome.REJECTED),
        ({}, None, SubmissionOutcome.UNKNOWN),
        ({"result": "success"}, None, SubmissionOutcome.UNKNOWN),
    ],
)
async def test_rejection_and_missing_completion_are_distinct(ack, status, outcome):
    device = device_with(
        lambda request: httpx.Response(
            200, json=ack if request.method == "POST" else {"sms_cmd_status_result": status}
        )
    )
    try:
        assert (await submit(device)).outcome is outcome
    finally:
        await device.close()


@pytest.mark.parametrize("phase", ["post", "completion"])
async def test_transport_failure_after_post_is_unknown_and_blocks_further_device_writes(phase):
    posts = []

    def respond(request):
        if request.method == "POST":
            posts.append(request)
            if phase == "post":
                raise httpx.ReadTimeout("fictional failure", request=request)
            return httpx.Response(200, json={"result": "success"})
        raise httpx.ConnectError("fictional failure", request=request)

    device = device_with(respond)
    try:
        assert (await submit(device)).outcome is SubmissionOutcome.UNKNOWN
        again = await submit(device)
        assert again.outcome is SubmissionOutcome.NOT_SUBMITTED and again.reason is SubmissionReason.BUSY
        assert len(posts) == 1
    finally:
        await device.close()


async def test_budget_includes_lock_wait_without_posting():
    posts = []
    device = device_with(lambda request: posts.append(request), send_timeout_seconds=0.01)
    try:
        async with device._operation_lock:
            result = await submit(device)
        assert result.outcome is SubmissionOutcome.NOT_SUBMITTED
        assert result.reason is SubmissionReason.TIMEOUT and posts == []
    finally:
        await device.close()


async def test_initial_ack_without_completion_expires_as_unknown():
    device = device_with(
        lambda request: httpx.Response(
            200, json={"result": "success"} if request.method == "POST" else {"sms_cmd_status_result": "1"}
        ),
        send_timeout_seconds=0.02,
    )
    try:
        result = await submit(device)
        assert result.outcome is SubmissionOutcome.UNKNOWN and result.reason is SubmissionReason.TIMEOUT
    finally:
        await device.close()


async def test_cancellation_during_post_propagates_and_latches_uncertainty():
    entered = asyncio.Event()

    async def respond(request):
        entered.set()
        await asyncio.Event().wait()

    device = device_with(respond)
    task = asyncio.create_task(submit(device))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await submit(device)).reason is SubmissionReason.BUSY
    finally:
        await device.close()


@pytest.mark.parametrize(
    "text,encoding", [("😀", SmsEncoding.UCS2), ("ب", SmsEncoding.GSM7), ("x" * 161, SmsEncoding.GSM7)]
)
async def test_invalid_prepared_text_never_posts_or_truncates(text, encoding):
    requests = []
    device = device_with(lambda request: requests.append(request))
    try:
        result = await submit(device, replace(SMS, text=text, encoding=encoding))
        assert result.outcome is SubmissionOutcome.NOT_SUBMITTED
        assert result.reason is SubmissionReason.INVALID_INPUT and requests == []
    finally:
        await device.close()


async def test_preflight_wrong_model_prevents_post():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text="DEVICE: 'datacard/OTHER'")

    device = ZteMf833tDevice(
        CellularDeviceId("wrong-model"), ZteMf833tSettings(), transport=httpx.MockTransport(respond)
    )
    try:
        result = await submit(device)
        assert result.outcome is SubmissionOutcome.NOT_SUBMITTED
        assert result.reason is SubmissionReason.MODEL_MISMATCH
        assert len(requests) == 1 and requests[0].method == "GET"
    finally:
        await device.close()
