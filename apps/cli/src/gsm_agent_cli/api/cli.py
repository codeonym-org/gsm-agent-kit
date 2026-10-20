import argparse
import re
import sys
from pathlib import Path
from typing import NoReturn
from uuid import UUID


class OperatorArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default error can echo unknown arguments, including an
        # accidentally supplied credential. Help documents the accepted inputs.
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: invalid arguments; use --help for usage.\n")


def device_id(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value):
        raise argparse.ArgumentTypeError(
            "device ID must contain 1–64 letters, digits, underscores or hyphens"
        )
    return value


def request_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise argparse.ArgumentTypeError("request ID must be a UUID") from None


def page_limit(value: str) -> int:
    try:
        result = int(value)
        if 1 <= result <= 200:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("limit must be an integer between 1 and 200")


def page_offset(value: str) -> int:
    try:
        result = int(value)
        if result >= 0:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("offset must be a nonnegative integer")


def build_parser() -> argparse.ArgumentParser:
    parser = OperatorArgumentParser(
        prog="gsm-agent",
        description="Query the GSM Agent Kit backend. Successful results are JSON; errors go to stderr.",
        epilog="Global options precede the command. Configuration defaults to .env in the working directory.",
        allow_abbrev=False,
    )
    parser.add_argument("--env-file", type=Path, help="Use this env file instead of ./.env")
    parser.add_argument("--api-url", help="Backend HTTP(S) origin (GSM_CLI__API_URL)")
    parser.add_argument("--timeout", help="Network phase timeout, 1–120 seconds (GSM_CLI__TIMEOUT_SECONDS)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, path, help_text in (
        ("health", "/health", "Check backend process health; does not establish device readiness"),
        ("runtime", "/api/runtime", "Read recorded background-worker status without probing devices"),
        ("adapters", "/api/adapters", "List installed adapter manifests and verification evidence"),
        ("devices", "/api/devices", "List logical devices with declared capabilities and observations"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(path=path, many=name not in {"health", "runtime"}, paginated=False)
    for name, suffix, help_text, many in (
        ("device", "", "Inspect a logical device and its adapter", False),
        ("status", "/status", "Read device status and capability availability", False),
        ("inbox", "/messages", "Read stored inbox messages without triggering ingestion", True),
        ("assistant", "/assistant", "Read assistant enablement, dry-run and job counts", False),
        ("jobs", "/assistant/jobs", "Read stored automatic-reply jobs", True),
        ("submission", "/submissions/{request_id}", "Look up submission acceptance; never resubmit", False),
        ("balance", "/balance", "Explicitly consult carrier balance; no arbitrary USSD or purchase", False),
    ):
        command = commands.add_parser(name, help=help_text, description=help_text)
        command.add_argument("device_id", type=device_id, help="Logical device ID from 'devices'")
        command.set_defaults(path="/api/devices/{device_id}" + suffix, many=many, paginated=many)
        if many:
            command.add_argument(
                "--limit", type=page_limit, default=50, help="Page size, 1–200 (default: 50)"
            )
            command.add_argument("--offset", type=page_offset, default=0, help="Row offset (default: 0)")
        if name == "submission":
            command.add_argument("request_id", type=request_id, help="Existing durable submission UUID")
    return parser
