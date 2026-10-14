import asyncio

import httpx
import pytest

from gsm_agent.domain.errors import ModemConnectionError, SmsSendFailedError, SmsSendUncertainError
from gsm_agent.domain.sms import PhoneNumber
from gsm_agent.infra.modem.zte import ZteModem


def sms(id: str, text: str = "مرحبا", tag: str = "1", **extra):
    return {
        "id": id,
        "number": "+212600000000",
        "content": text.encode("utf-16-be").hex(),
        "tag": tag,
        "date": "26,10,13,10,00,00,+4",
        **extra,
    }


async def test_inbox_pagination_unicode_sent_filter_and_multipart():
    def respond(request):
        page = request.url.params["page"]
        rows = [sms("1"), sms("2", tag="2")] if page == "0" else [sms("3", received_all_concat_sms="0")]
        return httpx.Response(200, json={"messages": rows})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        messages = await ZteModem(client, page_size=2).list_messages()
    assert [m.modem_id for m in messages] == ["1", "3"]
    assert messages[0].content == "مرحبا"
    assert not messages[1].complete


async def test_inbox_refuses_truncation_and_login_page():
    for response in ({"messages": [sms("1")]}, {"loginfo": "no"}):
        async with httpx.AsyncClient(
            base_url="http://modem",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response)),
        ) as client:
            with pytest.raises(ModemConnectionError):
                await ZteModem(client, page_size=1, max_pages=2).list_messages()


@pytest.mark.parametrize(
    "outcome,expected", [("3", None), ("2", SmsSendFailedError), ("0", SmsSendUncertainError)]
)
async def test_send_encodes_form_and_waits_for_completion(monkeypatch, outcome, expected):
    captured = []

    async def no_wait(seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    def respond(request):
        captured.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"result": "success"})
        return httpx.Response(200, json={"sms_cmd_status_result": outcome})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        modem = ZteModem(client, send_timeout=0.01)
        if expected:
            with pytest.raises(expected):
                await modem.send_sms(PhoneNumber("+212600000000"), "مرحبا")
        else:
            await modem.send_sms(PhoneNumber("+212600000000"), "مرحبا")
    from urllib.parse import parse_qs

    body = parse_qs(captured[0].content.decode())
    assert body["Number"] == ["+212600000000"]
    assert body["MessageBody"] == ["مرحبا".encode("utf-16-be").hex().upper()]
    assert body["encode_type"] == ["UNICODE"]
    assert captured[1].url.params["sms_cmd"] == "4"


async def test_send_transport_timeout_is_uncertain():
    def respond(request):
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(SmsSendUncertainError):
            await ZteModem(client).send_sms(PhoneNumber("+212600000000"), "hello")
