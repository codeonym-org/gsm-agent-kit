# gsm-agent-cli

Query-only operator client for a running GSM Agent Kit backend. Device access,
CQRS handlers, durable workflows and ownership stay in the server. The CLI does
not need adapter libraries, USB permissions or a second device connection.

## Run locally

From the repository root:

```bash
uv sync --locked --all-packages --all-extras
uv run --no-sync gsm-agent --help
uv run --no-sync gsm-agent devices
uv run --no-sync python -m gsm_agent_cli devices
```

Start the [backend](../server/README.md) or the
[production console stack](../../deploy/compose/README.md#production-console)
separately. The CLI never starts services. `--no-sync` preserves the shared
development environment when a backend is already using it.

For a separate installed client, `uv tool install ./apps/cli` installs only the
CLI and its HTTP/configuration dependencies. No package has been published.

## Configuration

The default env file is `.env` in the current working directory. Run from the
repository root to share its existing configuration, or pass an explicit
`--env-file /path/to/operator.env` before the command.

| Key | Default | Purpose |
| --- | --- | --- |
| `GSM_CLI__API_URL` | `http://127.0.0.1:8000` | Backend HTTP(S) origin, including an optional port |
| `GSM_CLI__TIMEOUT_SECONDS` | `35` | Connect/read/write/pool timeout per network phase, between 1 and 120 seconds |
| `GSM_API_TOKEN` | unset | Existing backend bearer token; omitted when empty |

An API URL is an origin, with no credentials, query, fragment or path prefix.
Use `http://127.0.0.1:8080` to query through the production console proxy. Use
HTTPS when connecting across an untrusted network. The default timeout exceeds
the backend's default balance consultation and cleanup budget; increase it if
you increase the server's balance deadline. A CLI timeout never proves a carrier
consultation has stopped.

Explicit `--api-url` / `--timeout` options override process environment variables,
which override the env file, which overrides defaults. Missing default `.env`
is allowed; an explicitly selected missing/unreadable file is an error. Env-file
values are literal, without `${VARIABLE}` interpolation. No credential argument
is provided; keep the token in the protected env file or process environment.
HTTP proxy and certificate environment settings are ignored (`trust_env=False`);
redirects and retries are disabled.

## Queries

Global options precede the command. Successful output is pretty-printed JSON on
stdout, suitable for `jq`. Strings are JSON-escaped, including terminal control
characters from messages or carrier responses. No files are written.

```bash
uv run --no-sync gsm-agent health
uv run --no-sync gsm-agent adapters
uv run --no-sync gsm-agent devices
uv run --no-sync gsm-agent device zte-device
uv run --no-sync gsm-agent status zte-device
uv run --no-sync gsm-agent inbox zte-device --limit 25 --offset 0
uv run --no-sync gsm-agent assistant zte-device
uv run --no-sync gsm-agent jobs zte-device --limit 25 --offset 0
uv run --no-sync gsm-agent submission zte-device 242b8428-257d-4eec-bb2c-30ffb37db901
uv run --no-sync gsm-agent --api-url http://127.0.0.1:8080 balance zte-device
```

Use the logical ID returned by `devices`; the UUID in the submission example is
fictional and must be replaced with an existing request ID. Pagination supports
limits 1–200 and nonnegative offsets. Empty inventory/inbox/jobs return `[]`.
Device IDs, UUIDs, pagination and configuration are validated before HTTP access.

`health` observes the backend process; it does not establish SIM readiness or
provider connectivity. Device output retains model adapter identity, declared
capability support and observed availability as separate data. `assistant`
returns automatic-reply enablement, dry-run mode and job counts; `jobs` returns
job metadata. Inbox and submission queries read durable state without triggering
ingestion, AI generation or sending. Submission acceptance is not delivery;
unknown or blocked outcomes are preserved and repeated lookups never resubmit.

Only `balance` initiates a carrier consultation, explicitly on demand. It does
not expose arbitrary USSD, purchase an offer or follow a menu. The current
ZTE MF833T adapter does not support balance, so it returns exit code 5. This CLI
slice has no SMS send, ingest, retry, configuration-write or watch command.

## Errors

Failures emit a concise message on stderr and no success JSON. Remote error
bodies, credentials, redirects' destinations and transport exception details
are not echoed. Responses must be JSON of the expected top-level shape and fit
within 8 MiB; choose a smaller page when needed.

| Exit code | Meaning |
| --- | --- |
| `0` | Successful query or help |
| `2` | Invalid arguments, configuration or env file |
| `3` | Transport/timeout failure, invalid or oversized response |
| `4` | Authentication/authorization denied (401/403) |
| `5` | Capability unsupported (501) |
| `6` | Device or record missing (404) |
| `7` | Busy/conflicting operation (409) |
| `8` | Other HTTP failure, including a refused redirect |
| `130` | Interrupted query |

There is no automatic retry, including for balance or a timeout. Fix the cause
and decide explicitly whether another consultation is appropriate. Successful
JSON can contain private SMS data and phone numbers; store it accordingly.

## Verification

```bash
uv run --no-sync pytest apps/cli/tests -q
```

Tests cover configuration precedence, authentication, routing, validation,
sanitized failures and installed entry points. Assembled tests run the CLI as
a subprocess against the actual FastAPI/Dishka/Mediary backend and temporary
SQLite state, with a simulated cellular device. Accepted and unknown submission
lookups retain one recorded attempt. Servers use ephemeral loopback ports and
are stopped afterward. No local secret files, hardware or paid services are used.

Python import: `gsm_agent_cli`.
