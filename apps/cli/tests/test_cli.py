import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from gsm_agent_cli.infra import http as transport_module
from gsm_agent_cli.runtime.app import run

REQUEST_ID = "242b8428-257d-4eec-bb2c-30ffb37db901"


@pytest.mark.parametrize(
    "argv,path,payload,params",
    [
        (["health"], "/health", {"status": "ok"}, {}),
        (["adapters"], "/api/adapters", [{"capabilities": ["device.status.read"]}], {}),
        (["devices"], "/api/devices", [{"device_id": "demo-device"}], {}),
        (["device", "demo-device"], "/api/devices/demo-device", {"observation": None}, {}),
        (["status", "demo-device"], "/api/devices/demo-device/status", {"availability": "busy"}, {}),
        (
            ["inbox", "demo-device", "--limit", "25", "--offset", "50"],
            "/api/devices/demo-device/messages",
            [{"body": "Synthetic SMS\u001b]0;untrusted title\u0007"}],
            {"limit": "25", "offset": "50"},
        ),
        (["assistant", "demo-device"], "/api/devices/demo-device/assistant", {"dry_run": True}, {}),
        (
            ["jobs", "demo-device"],
            "/api/devices/demo-device/assistant/jobs",
            [],
            {"limit": "50", "offset": "0"},
        ),
        (
            ["submission", "demo-device", REQUEST_ID],
            f"/api/devices/demo-device/submissions/{REQUEST_ID}",
            {"complete": False, "accepted_parts": 0, "blocked": True, "parts": [{"state": "unknown"}]},
            {},
        ),
        (
            ["balance", "demo-device"],
            "/api/devices/demo-device/balance",
            {"raw_text": "Synthetic credit"},
            {},
        ),
    ],
)
def test_queries_route_once_with_auth_and_preserve_json(argv, path, payload, params, monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("GSM_API_TOKEN", "synthetic-api-token")

    def respond(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == path
        assert dict(request.url.params) == params
        assert request.headers["Authorization"] == "Bearer synthetic-api-token"
        assert not request.content
        assert request.extensions["timeout"]["read"] == 35
        return httpx.Response(200, json=payload)

    assert run(argv, transport=httpx.MockTransport(respond)) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == payload and not captured.err
    assert "\x1b" not in captured.out and "synthetic-api-token" not in captured.out
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,exit_code",
    [(401, 4), (403, 4), (501, 5), (404, 6), (409, 7), (422, 8), (503, 8), (504, 8), (500, 8)],
)
def test_backend_errors_never_echo_body_and_never_retry(status, exit_code, capsys):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"detail": "synthetic-secret\u001b[2J"})

    assert run(["balance", "demo-device"], transport=httpx.MockTransport(respond)) == exit_code
    captured = capsys.readouterr()
    assert not captured.out and captured.err
    assert "synthetic-secret" not in captured.err and "\x1b" not in captured.err
    assert len(calls) == 1


def test_redirect_does_not_forward_authentication_to_another_origin(monkeypatch, capsys):
    calls = []
    monkeypatch.setenv("GSM_API_TOKEN", "synthetic-api-token")

    def respond(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://elsewhere.invalid?synthetic-secret"})

    assert run(["devices"], transport=httpx.MockTransport(respond)) == 8
    assert len(calls) == 1
    assert "redirect" in capsys.readouterr().err


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError])
def test_transport_failures_are_sanitized_and_not_retried(error, capsys):
    calls = []

    def respond(request):
        calls.append(request)
        raise error("synthetic-secret", request=request)

    assert run(["devices"], transport=httpx.MockTransport(respond)) == 3
    captured = capsys.readouterr()
    assert not captured.out and "synthetic-secret" not in captured.err
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body,content_type",
    [
        (b"<html>synthetic-secret</html>", "text/html"),
        (b"{broken", "application/json"),
        (b"null", "application/json"),
        (b"{}", "application/json"),
        (b"[NaN]", "application/json"),
        (b'[{"a": Infinity}]', "application/json"),
        (b'[{"a": 1e999}]', "application/json"),
    ],
)
def test_invalid_backend_output_is_not_printed(body, content_type, capsys):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=body, headers={"Content-Type": content_type})
    )
    assert run(["devices"], transport=transport) == 3
    captured = capsys.readouterr()
    assert not captured.out and "JSON response" in captured.err and "synthetic-secret" not in captured.err


def test_response_size_limit(monkeypatch, capsys):
    monkeypatch.setattr(transport_module, "MAX_RESPONSE_BYTES", 10)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[{"large": "x" * 100}]))
    assert run(["devices"], transport=transport) == 3
    assert "smaller page" in capsys.readouterr().err


def test_interruption_does_not_retry(capsys):
    calls = []

    def respond(request):
        calls.append(request)
        raise KeyboardInterrupt()

    assert run(["balance", "demo-device"], transport=httpx.MockTransport(respond)) == 130
    captured = capsys.readouterr()
    assert not captured.out and "Cancelled" in captured.err
    assert len(calls) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "../elsewhere"],
        ["status", "id?token=secret"],
        ["submission", "demo-device", "bad-uuid"],
        ["inbox", "demo-device", "--limit", "201"],
        ["inbox", "demo-device", "--limit", "0"],
        ["jobs", "demo-device", "--offset", "-1"],
        ["jobs", "demo-device", "--offset", "synthetic-secret"],
        ["--token", "synthetic-secret", "devices"],
        ["send", "synthetic-secret"],
    ],
)
def test_invalid_arguments_fail_before_http_and_are_not_echoed(argv, capsys):
    def unexpected(request):
        pytest.fail("Invalid input must not reach the backend")

    with pytest.raises(SystemExit) as error:
        run(argv, transport=httpx.MockTransport(unexpected))
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out and "synthetic-secret" not in captured.err


def test_bad_configuration_never_sends_a_request_or_echoes_values(monkeypatch, capsys):
    monkeypatch.setenv("GSM_CLI__API_URL", "http://user:synthetic-secret@backend.invalid")

    def unexpected(request):
        pytest.fail("Invalid configuration must not reach the backend")

    assert run(["devices"], transport=httpx.MockTransport(unexpected)) == 2
    captured = capsys.readouterr()
    assert not captured.out and "synthetic-secret" not in captured.err


def test_proxy_environment_is_ignored_and_options_override_file(monkeypatch, tmp_path, capsys):
    path = tmp_path / "synthetic.env"
    path.write_text("GSM_CLI__API_URL=http://file.invalid\nGSM_API_TOKEN=synthetic-token\n")
    monkeypatch.setenv("HTTP_PROXY", "http://user:synthetic-proxy-secret@proxy.invalid")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.host == "override.invalid"
        assert request.headers["authorization"] == "Bearer synthetic-token"
        assert request.extensions["timeout"]["connect"] == 2.5
        return httpx.Response(200, json=[])

    assert (
        run(
            ["--env-file", str(path), "--api-url", "https://override.invalid", "--timeout", "2.5", "devices"],
            transport=httpx.MockTransport(respond),
        )
        == 0
    )
    assert len(calls) == 1 and json.loads(capsys.readouterr().out) == []


def test_entry_points_show_help_without_loading_configuration(tmp_path, monkeypatch):
    # Even an unreadable/invalid default env file cannot prevent help.
    (tmp_path / ".env").write_bytes(b"GSM_API_TOKEN=\xff")
    monkeypatch.setenv("GSM_CLI__API_URL", "invalid-synthetic-value")
    executables = [
        [sys.executable, "-m", "gsm_agent_cli", "--help"],
        [
            str(Path(sys.executable).parent / ("gsm-agent.exe" if sys.platform == "win32" else "gsm-agent")),
            "--help",
        ],
    ]
    for command in executables:
        result = subprocess.run(
            command, cwd=tmp_path, capture_output=True, text=True, check=False, timeout=10
        )
        assert result.returncode == 0 and "balance" in result.stdout and "--env-file" in result.stdout
        assert not result.stderr and "invalid-synthetic-value" not in result.stdout
