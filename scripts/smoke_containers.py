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
REALTIME_CHECK = """
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';
assert.notEqual(process.getuid(), 0);
assert(existsSync('/app/index.mjs'));
for (const path of ['/build', '/app/node_modules', '/app/server', '/app/.env'])
    assert(!existsSync(path), path);
console.info('PASS: bundled gateway is non-root with no workspace/node_modules/config file');
"""
CONSOLE_CHECK = (
    'test "$(id -u)" != 0 && test ! -d /build && test ! -d /srv/node_modules '
    "&& test ! -f /srv/.env && ! command -v node && caddy version >/dev/null "
    '&& echo "PASS: static console is non-root with no Node/workspace/config file"'
)


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
        str(ROOT / "deploy/compose/console.yaml"),
        "-f",
        str(ROOT / "deploy/compose/smoke.yaml"),
        "--profile",
        "smoke",
        "--profile",
        "console",
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
            compose("build", "zte", "realtime", "console")
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
        for image, executable, arguments in (
            ("realtime", "node", ["--input-type=module", "-e", REALTIME_CHECK]),
            ("console", "/bin/sh", ["-c", CONSOLE_CHECK]),
        ):
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--entrypoint",
                    executable,
                    f"gsm-agent-kit/{image}:local",
                    *arguments,
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
        compose("up", "-d", "--wait", "--wait-timeout", "90", "console")
        compose("run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "console")
        compose("run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "exercise")
        compose("down")
        compose("up", "-d", "--wait", "--wait-timeout", "90", "console")
        compose("run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "persist")
        compose("up", "-d", "--wait", "--wait-timeout", "90", "console", dry_run=True)
        compose(
            "run", "--rm", "--no-deps", "smoke-check", "python", "/smoke/check.py", "dry-run", dry_run=True
        )
        compose(
            "run",
            "--rm",
            "--no-deps",
            "smoke-check",
            "python",
            "/smoke/check.py",
            "manual-proxy",
            dry_run=True,
        )
        print("PASS: production console/realtime, SMS flow, restart persistence, dry-run and deduplication")
    except (subprocess.CalledProcessError, KeyboardInterrupt):
        # These logs belong only to this uniquely named synthetic fixture project.
        subprocess.run([*command, "logs", "--tail", "80"], cwd=ROOT, env=env, check=False)
        raise
    finally:
        subprocess.run([*command, "down", "--volumes", "--remove-orphans"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    main()
