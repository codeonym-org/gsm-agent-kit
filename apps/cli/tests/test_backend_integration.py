"""Installed CLI against the real API/DI/CQRS/SQLite on an ephemeral loopback port."""

import asyncio
import json
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from uuid import UUID

import pytest
import uvicorn
from gsm_agent.application.text import SmsLimits, prepare_sms
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxItem, InboxSnapshot, InboxSource, SmsAddress
from gsm_agent_core.domain.submission import (
    SmsDestination,
    SmsSendConstraints,
    SmsSubmissionResult,
    SubmissionOutcome,
)
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import (
    BalanceSettings,
    DeviceSettings,
    InboxSettings,
    Settings,
    SubmissionSettings,
)
from gsm_agent_sqlite import SqliteInboxStore, SqliteSubmissionStore
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

ACCEPTED_ID = UUID("ba6b43b9-47f2-45f7-b9f9-f5c4371b629e")
UNKNOWN_ID = UUID("46e253a4-18bc-48bb-80c9-e6bd76a980e8")


class FixtureSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="UNUSED_CLI_FIXTURE_")


async def seed_ledgers(path):
    device = CellularDeviceId("cli-fixture")
    inbox = await SqliteInboxStore.open(path / "inbox.db")
    submissions = await SqliteSubmissionStore.open(path / "submissions.db")
    try:
        now = datetime.now(UTC)
        source = InboxSource(device, "fixture", "memory")
        await inbox.ingest(InboxSnapshot(source, "fixture", now, now, ()))
        await inbox.ingest(
            InboxSnapshot(
                source,
                "fixture",
                now,
                now,
                (
                    InboxItem(
                        "1",
                        SmsAddress.from_sender("+212600000000"),
                        "Synthetic incoming SMS",
                        "fixture",
                        True,
                    ),
                ),
            )
        )
        plan = prepare_sms("Synthetic outgoing SMS", SmsLimits(), SmsSendConstraints())
        for request_id, outcome in (
            (ACCEPTED_ID, SubmissionOutcome.ACCEPTED),
            (UNKNOWN_ID, SubmissionOutcome.UNKNOWN),
        ):
            await submissions.create(
                device, request_id, SmsDestination("+212600000000"), str(request_id), plan
            )
            attempt = await submissions.begin_attempt(device, request_id, 0)
            assert attempt is not None
            await submissions.finish_attempt(
                SmsSubmissionResult(attempt.message_id, attempt.attempt_id, outcome)
            )
    finally:
        await inbox.close()
        await submissions.close()


@pytest.fixture
def api_server(tmp_path, request):
    asyncio.run(seed_ledgers(tmp_path))
    config = FixtureSettings(
        api_token=SecretStr("synthetic-cli-token"),
        device=DeviceSettings(id="cli-fixture", simulated_balance_enabled=getattr(request, "param", True)),
        balance=BalanceSettings(carrier="simulated"),
        inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db"),
        submissions=SubmissionSettings(enabled=True, database_path=tmp_path / "submissions.db"),
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(create_app(config), loop="asyncio", log_config=None, access_log=False)
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "Synthetic backend did not start"
        (tmp_path / ".env").write_text(f"GSM_CLI__API_URL={url}\nGSM_API_TOKEN=synthetic-cli-token\n")
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "Synthetic backend did not stop"


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "gsm_agent_cli", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_installed_cli_reads_real_backend_and_durable_outcomes_without_resubmission(api_server):
    results = {}
    for command in (
        "health",
        "adapters",
        "devices",
        "device",
        "status",
        "inbox",
        "assistant",
        "jobs",
        "balance",
    ):
        args = (command,) if command in {"health", "adapters", "devices"} else (command, "cli-fixture")
        result = invoke(*args)
        assert result.returncode == 0, result.stderr
        assert not result.stderr and "synthetic-cli-token" not in result.stdout
        results[command] = json.loads(result.stdout)
    assert results["health"]["status"] == "ok"
    assert results["devices"][0]["device_id"] == "cli-fixture"
    assert set(results["device"]["adapter"]["capabilities"]) == {"device.status.read", "carrier.balance.read"}
    assert results["status"]["availability"] == "ready"
    assert results["inbox"][0]["body"] == "Synthetic incoming SMS"
    assert results["inbox"][0]["replyable"]
    assert results["assistant"] == {"auto_reply": False, "dry_run": True, "jobs": {}}
    assert results["jobs"] == []
    assert results["balance"]["raw_text"]
    assert json.loads(invoke("inbox", "cli-fixture", "--offset", "1").stdout) == []
    for request_id, state, accepted, blocked in (
        (ACCEPTED_ID, "accepted", 1, False),
        (UNKNOWN_ID, "unknown", 0, True),
    ):
        first = invoke("submission", "cli-fixture", str(request_id))
        again = invoke("submission", "cli-fixture", str(request_id))
        assert first.returncode == again.returncode == 0
        payload = json.loads(first.stdout)
        assert json.loads(again.stdout) == payload
        assert payload["accepted_parts"] == accepted and payload["blocked"] == blocked
        assert payload["parts"][0]["state"] == state
        assert len(payload["parts"][0]["attempts"]) == 1
        assert "delivered" not in payload
    missing = invoke("status", "absent")
    assert missing.returncode == 6 and not missing.stdout


def test_installed_cli_reports_authentication_failure_without_remote_details(api_server, monkeypatch):
    monkeypatch.setenv("GSM_API_TOKEN", "synthetic-wrong-token")
    result = invoke("devices")
    assert result.returncode == 4 and not result.stdout
    assert "GSM_API_TOKEN" in result.stderr
    assert "synthetic-wrong-token" not in result.stderr and "Traceback" not in result.stderr


@pytest.mark.parametrize("api_server", [False], indirect=True)
def test_installed_cli_reports_unsupported_balance(api_server):
    result = invoke("balance", "cli-fixture")
    assert result.returncode == 5 and not result.stdout
    assert "does not support" in result.stderr
