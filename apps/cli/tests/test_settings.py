from pathlib import Path

import pytest
from gsm_agent_cli.runtime.settings import ConfigurationError, Settings


def test_file_environment_and_explicit_precedence_without_mutating_environment(tmp_path):
    path = tmp_path / "operator.env"
    path.write_text(
        "GSM_CLI__API_URL=http://file.invalid:8000\n"
        "GSM_CLI__TIMEOUT_SECONDS=40\n"
        "GSM_API_TOKEN='literal-${UNRELATED_SECRET}'\n"
        "GSM_ASSISTANT__API_KEY=unrelated-synthetic-key\n"
    )
    config = Settings.load(path, environ={"UNRELATED_SECRET": "do-not-interpolate"})
    assert config.api_url == "http://file.invalid:8000"
    assert config.timeout_seconds == 40
    assert config.api_token == "literal-${UNRELATED_SECRET}"
    assert "literal-" not in repr(config)
    config = Settings.load(
        path,
        environ={"GSM_CLI__API_URL": "https://process.invalid", "GSM_API_TOKEN": "process-token"},
    )
    assert config.api_url == "https://process.invalid" and config.api_token == "process-token"
    explicit = Settings.load(path, "http://127.0.0.1:8080/", "1.5", environ={"GSM_CLI__API_URL": "bad"})
    assert explicit.api_url == "http://127.0.0.1:8080" and explicit.timeout_seconds == 1.5
    assert Settings.load(path, environ={"GSM_API_TOKEN": ""}).api_token is None


def test_default_file_and_no_file_defaults(tmp_path):
    assert Settings.load(environ={}) == Settings("http://127.0.0.1:8000", 35)
    (tmp_path / ".env").write_text("GSM_CLI__API_URL=http://localhost:8080\nGSM_API_TOKEN=fictional-token\n")
    assert Settings.load(environ={}).api_url == "http://localhost:8080"
    assert Settings.load(environ={}).api_token == "fictional-token"


@pytest.mark.parametrize(
    "url",
    [
        "ftp://backend.invalid",
        "backend.invalid",
        "http://user:synthetic-secret@backend.invalid",
        "http://backend.invalid/api",
        "http://backend.invalid?token=synthetic-secret",
        "http://backend.invalid#synthetic-secret",
        "http://backend.invalid?",
        "http://backend.invalid#",
        "http://backend.invalid:bad",
        " http://backend.invalid",
        "http://back\nend.invalid",
    ],
)
def test_invalid_url_values_are_never_echoed(url):
    with pytest.raises(ConfigurationError) as error:
        Settings.load(api_url=url, environ={})
    assert "synthetic-secret" not in str(error.value)


@pytest.mark.parametrize("timeout", ["0", "121", "nan", "inf", "-1", "synthetic-secret"])
def test_timeout_is_finite_bounded_and_redacted(timeout):
    with pytest.raises(ConfigurationError, match="Timeout must") as error:
        Settings.load(timeout_seconds=timeout, environ={})
    assert "synthetic-secret" not in str(error.value)


def test_missing_explicit_env_file_and_invalid_encoding_are_errors(tmp_path):
    with pytest.raises(ConfigurationError):
        Settings.load(Path("missing-synthetic-file"), environ={})
    with pytest.raises(ConfigurationError):
        Settings.load(tmp_path, environ={})
    broken = tmp_path / "bad.env"
    broken.write_bytes(b"GSM_API_TOKEN=\xff")
    with pytest.raises(ConfigurationError, match="Cannot read"):
        Settings.load(broken, environ={})


@pytest.mark.parametrize("token", ["synthetic secret", "synthetic\r\nsecret", "synthetic-é-secret"])
def test_invalid_bearer_token_reports_only_the_key(token):
    with pytest.raises(ConfigurationError) as error:
        Settings.load(environ={"GSM_API_TOKEN": token})
    assert token not in str(error.value)
