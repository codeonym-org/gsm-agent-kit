import asyncio
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from gsm_agent import webapp
from gsm_agent.di.container import build_container
from gsm_agent.domain.balance import BalanceCode
from gsm_agent.domain.errors import BalanceTimeoutError, BalanceUnavailableError
from gsm_agent.infra.modem.zte import ZteModem
from gsm_agent.runtime.config import ListenerConfig, ModemConfig, StorageConfig
from gsm_agent.runtime.settings import Settings
from tests.test_application import FakeAgent, FakeModem, fake_provider


async def test_balance_ussd_pending_hex_decoding_and_session_cleanup(monkeypatch):
    calls = []
    flags = iter(["13", "15", "16"])

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    def respond(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"result": "success"})
        if request.url.params["cmd"] == "ussd_write_flag":
            return httpx.Response(200, json={"ussd_write_flag": next(flags)})
        return httpx.Response(
            200,
            json={"ussd_data": "رصيدك 12 DH".encode("utf-16-be").hex(), "ussd_action": "1", "ussd_dcs": "72"},
        )

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        result = await ZteModem(client).consult_balance(BalanceCode())
    assert result.text == "رصيدك 12 DH"
    assert result.session_open
    form = parse_qs(next(call for call in calls if call.method == "POST").content.decode())
    assert form["USSD_send_number"] == ["*120*30#"]
    assert form["USSD_operator"] == ["ussd_send"]
    assert parse_qs(calls[-1].content.decode())["USSD_operator"] == ["ussd_cancel"]


@pytest.mark.parametrize(
    "flag,expected",
    [
        ("99", BalanceUnavailableError),
        ("1", BalanceUnavailableError),
        ("3", BalanceTimeoutError),
        ("41", BalanceUnavailableError),
    ],
)
async def test_balance_errors_cleanup_and_no_resend(flag, expected):
    posts = []

    def respond(request):
        if request.method == "POST":
            posts.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"result": "success"})
        return httpx.Response(200, json={"ussd_write_flag": flag})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(expected):
            await ZteModem(client).consult_balance(BalanceCode())
    assert [p["USSD_operator"][0] for p in posts] == ["ussd_send", "ussd_cancel"]


async def test_balance_deadline_covers_polling_and_cleanup():
    posts = []

    def respond(request):
        if request.method == "POST":
            posts.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"result": "success"})
        return httpx.Response(200, json={"ussd_write_flag": "15" if posts else "13"})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(BalanceTimeoutError):
            await ZteModem(client, ussd_timeout=0.01).consult_balance(BalanceCode())
    assert len(posts) == 2


async def test_balance_bad_response_never_guesses_zero():
    def respond(request):
        if request.method == "POST":
            return httpx.Response(200, json={"result": "success"})
        if request.url.params["cmd"] == "ussd_write_flag":
            return httpx.Response(200, json={"ussd_write_flag": "16"})
        return httpx.Response(200, json={"ussd_data": "not valid hex"})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(BalanceUnavailableError):
            await ZteModem(client).consult_balance(BalanceCode())


def test_balance_configured_code_and_timeout_http_mapping(tmp_path, monkeypatch):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        listener=ListenerConfig(enabled=False),
        modem=ModemConfig(balance_code="*120*20#"),
        storage=StorageConfig(path=tmp_path / "inbox.db"),
    )
    monkeypatch.setattr(
        webapp, "build_container", lambda config: build_container(config, fake_provider(modem, agent))
    )
    with TestClient(webapp.create_app(settings)) as client:
        assert client.get("/api/modem/balance").json()["code"] == "*120*20#"
        assert client.post("/api/modem/balance").json()["code"] == "*120*20#"

        async def timeout(code):
            raise BalanceTimeoutError("Carrier timed out")

        modem.consult_balance = timeout
        assert client.get("/api/modem/balance").status_code == 504


async def test_balance_recovers_stale_pending_session_before_sending(monkeypatch):
    posts = []
    flags = iter(["15", "15", "13", "16"])

    async def no_wait(seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    def respond(request):
        if request.method == "POST":
            posts.append(parse_qs(request.content.decode())["USSD_operator"][0])
            return httpx.Response(200, json={"result": "success"})
        if request.url.params["cmd"] == "ussd_write_flag":
            return httpx.Response(200, json={"ussd_write_flag": next(flags)})
        return httpx.Response(200, json={"ussd_data": "Solde 10 DH".encode("utf-16-be").hex()})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        result = await ZteModem(client).consult_balance(BalanceCode())
    assert result.text == "Solde 10 DH"
    assert posts == ["ussd_cancel", "ussd_send", "ussd_cancel"]


async def test_balance_is_a_query():
    from mediary.cqrs import Query

    from gsm_agent.application.queries.balance import ConsultBalance

    assert isinstance(ConsultBalance(), Query)


async def test_balance_stuck_session_does_not_submit_another_request():
    posts = []

    def respond(request):
        if request.method == "POST":
            posts.append(parse_qs(request.content.decode())["USSD_operator"][0])
            return httpx.Response(200, json={"result": "success"})
        return httpx.Response(200, json={"ussd_write_flag": "15"})

    async with httpx.AsyncClient(base_url="http://modem", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(BalanceUnavailableError, match="stuck pending"):
            await ZteModem(client).consult_balance(BalanceCode())
    assert posts == ["ussd_cancel"]
