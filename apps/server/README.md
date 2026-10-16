# gsm-agent-server

API transport, dependency injection and runtime composition.

The first slice exposes device and adapter inspection. Its hexagonal path is
API routes → Mediary queries → application ports → cellular-device adapters.
Dishka owns application and request scopes. Startup composes the selected
adapter eagerly; shutdown closes its resources, including after startup failure.

## Run

```bash
uv run --package gsm-agent-server --extra simulated gsm-agent-server
```

The built-in command binds to `127.0.0.1:8000`. Open `/docs` for the interactive
API. Run `gsm-agent-server --help` for options. To change host or port:

```bash
uv run --package gsm-agent-server --extra simulated gsm-agent-server --host 127.0.0.1 --port 8001
```

The simulated adapter is an optional package; install `gsm-agent-server[simulated]`
in a standalone environment. It does not represent verified physical hardware.
It currently supports only `device.status.read` and performs no external I/O.

## Configuration

Settings load from environment variables and an optional `.env` in the working
directory. Keep that file untracked. Nested adapter settings use `__`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GSM_DEVICE__ADAPTER` | `simulated` | Explicit adapter selection; currently only the simulated profile is implemented |
| `GSM_DEVICE__ID` | `demo-device` | Stable logical cellular device ID, independent of address or USB path |
| `GSM_DEVICE__SIMULATED_AVAILABILITY` | `ready` | `ready`, `busy`, `unavailable` or `unknown` |
| `GSM_QUERY_TIMEOUT_SECONDS` | `5` | Whole description/status query budget, positive and at most 30 seconds |
| `GSM_API_TOKEN` | unset | Optional Bearer token for `/api` routes; set it when exposing the API beyond localhost |

Invalid adapter selections and device IDs fail configuration. Unavailable
status preserves capability support. Secrets are not included in descriptions.

## API

```bash
curl http://127.0.0.1:8000/api/adapters
curl http://127.0.0.1:8000/api/devices
curl http://127.0.0.1:8000/api/devices/demo-device
curl http://127.0.0.1:8000/api/devices/demo-device/status
```

All operations use GET and CQRS queries. Unknown device IDs return 404;
unsupported status capability returns 501; a read deadline returns 504.
These responses have documented schemas in OpenAPI. `/health` reports process
health and configured adapter profile; it does not probe hardware.

Firmware observations, model compatibility evidence, hardware access and SMS
operations follow with the model-specific ZTE MF833T implementation.

Python import: `gsm_agent_server`.
