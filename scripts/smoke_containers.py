"""Build and verify an isolated Compose project, then remove only its fixtures."""

import argparse
import os
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "gsm-agent-kit/zte-mf833t:local"
RUNTIME_CHECK = """
import importlib.util
import os
from pathlib import Path
from gsm_agent_langchain import LangChainAgent
for name in ('gsm_agent_server', 'gsm_agent_zte_mf833t', 'gsm_agent_sqlite', 'gsm_agent_langchain'):
    assert importlib.util.find_spec(name) is not None, name
for name in ('pytest', 'gsm_agent_simulated', 'gsm_agent_serial_at', 'gsm_agent_modemmanager'):
    assert importlib.util.find_spec(name) is None, name
assert os.getuid() == 10001
assert not Path('/smoke').exists() and not Path('/build').exists()
assert not Path('/app/.env').exists()
LangChainAgent(model='openai/gpt-4.1-mini', api_key='synthetic-unused-key', instructions='Fixture only.')
print('PASS: production dependencies, non-root user and fixture/secret exclusion')
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-build", action="store_true", help="Use previously built local deployment images"
    )
    args = parser.parse_args()
    project = "gsm-smoke-" + uuid.uuid4().hex[:12]
    # Never load the user's .env or inherit GSM/Compose settings into synthetic tests.
    env = {key: value for key, value in os.environ.items() if not key.startswith(("GSM_", "COMPOSE_"))}
    command = [
        "docker",
        "compose",
        "--env-file",
        os.devnull,
        "-p",
        project,
        "-f",
        str(ROOT / "deploy/compose/smoke.yaml"),
        "--profile",
        "smoke",
    ]

    def compose(*arguments: str, dry_run: bool = False) -> None:
        subprocess.run(
            [*command, *arguments],
            cwd=ROOT,
            check=True,
            env={**env, "GSM_SMOKE_DRY_RUN": str(dry_run).lower()},
        )

    try:
        if not args.no_build:
            subprocess.run(
                [
                    "docker",
                    "build",
                    "--target",
                    "zte-mf833t",
                    "-t",
                    IMAGE,
                    "-f",
                    "deploy/images/server.Dockerfile",
                    ".",
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
            compose("build", "smoke-backend")
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                IMAGE,
                "python",
                "-c",
                RUNTIME_CHECK,
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        compose("up", "-d", "--wait", "--wait-timeout", "90", "smoke-backend")
        compose("run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "exercise")
        compose("down")
        compose("up", "-d", "--wait", "--wait-timeout", "90", "smoke-backend")
        compose("run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "persist")
        compose("up", "-d", "--wait", "--wait-timeout", "90", "smoke-backend", dry_run=True)
        compose(
            "run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "dry-run", dry_run=True
        )
        print("PASS: container SMS flow, restart persistence, conversation memory, dry-run and deduplication")
    except (subprocess.CalledProcessError, KeyboardInterrupt):
        # These logs belong only to this uniquely named synthetic fixture project.
        subprocess.run([*command, "logs", "--tail", "80"], cwd=ROOT, env=env, check=False)
        raise
    finally:
        subprocess.run([*command, "down", "--volumes", "--remove-orphans"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    main()
