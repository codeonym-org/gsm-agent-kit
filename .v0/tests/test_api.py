from fastapi.testclient import TestClient
from pydantic import SecretStr

from gsm_agent import webapp
from gsm_agent.di.container import build_container
from gsm_agent.runtime.config import ListenerConfig, StorageConfig
from gsm_agent.runtime.settings import Settings
from tests.test_application import FakeAgent, FakeModem, fake_provider


def test_api_auth_queries_commands_and_sse(tmp_path, monkeypatch):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "api.db"),
        listener=ListenerConfig(enabled=False),
        api_token=SecretStr("test-token"),
    )
    monkeypatch.setattr(
        webapp, "build_container", lambda config: build_container(config, fake_provider(modem, agent))
    )
    with TestClient(webapp.create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/messages").status_code == 401
        assert client.post("/api/modem/balance").status_code == 401
        headers = {"Authorization": "Bearer test-token"}
        assert client.get("/api/modem/status", headers=headers).json()["network_type"] == "LTE"
        balance = client.post("/api/modem/balance", headers=headers)
        assert balance.status_code == 200
        assert balance.json()["text"] == "Votre solde: 12,50 DH"
        assert balance.json()["code"] == "*120*30#"
        assert modem.balance_codes == ["*120*30#"]
        assert client.get("/api/messages?limit=0", headers=headers).status_code == 422
        body = {"messages": [{"role": "user", "content": "hello"}]}
        reply = client.post("/api/agent/invoke", json=body, headers=headers)
        assert reply.status_code == 200
        assert reply.json() == {"action": "reply", "text": "Bonjour!", "ignore_reason": None}
        streamed = client.post("/api/agent/stream", json=body, headers=headers)
        assert streamed.status_code == 200
        assert "event: text" in streamed.text
        assert "event: result" in streamed.text
        assert '"text":"Bonjour!"' in streamed.text
        receipt = client.post("/api/sms", json={"recipient": "+212600000000", "text": "hi"}, headers=headers)
        assert receipt.json()["state"] == "dry_run"
        assert modem.sends == []
        invalid = client.post(
            "/api/sms", json={"recipient": "+212600000000;123", "text": "hi"}, headers=headers
        )
        assert invalid.status_code == 422
        agent.fail = True
        assert client.post("/api/agent/stream", json=body, headers=headers).text.endswith(
            'event: error\ndata: {"detail":"Agent stream failed"}\n\n'
        )
