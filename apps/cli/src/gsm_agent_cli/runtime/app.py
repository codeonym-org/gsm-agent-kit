import json
import sys

import httpx

from gsm_agent_cli.api.cli import build_parser
from gsm_agent_cli.infra.http import ApiError, OperatorApi
from gsm_agent_cli.runtime.settings import ConfigurationError, Settings


def run(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.load(args.env_file, args.api_url, args.timeout)
        with OperatorApi(settings, transport=transport) as api:
            result = api.get(
                args.path.format(**vars(args)),
                params={"limit": args.limit, "offset": args.offset} if args.paginated else None,
                many=args.many,
            )
        # JSON escaping also prevents carrier/SMS terminal control sequences from
        # being interpreted when an operator prints the response directly.
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 0
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except ApiError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("Cancelled; no retry was attempted.", file=sys.stderr)
        return 130


def main() -> None:
    try:
        raise SystemExit(run())
    except BrokenPipeError:
        # Allow pipelines such as `gsm-agent devices | head` without a traceback.
        raise SystemExit(0) from None
