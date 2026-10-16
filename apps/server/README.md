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

For a ZTE MF833T reachable over HTTP:

```bash
GSM_DEVICE__ADAPTER=zte-mf833t GSM_DEVICE__ID=zte-device \
  uv run --package gsm-agent-server --extra zte-mf833t gsm-agent-server
```

Inspect `/api/devices/zte-device` and `/api/devices/zte-device/status`.
The `zte-mf833t` extra installs the model-specific adapter and HTTPX without
the simulated adapter, AT tools or ModemManager. In a standalone installation,
use `gsm-agent-server[zte-mf833t]` or the `gsm-agent-kit[zte-mf833t]` bundle.
Packages have not yet been published to a registry; these names describe built
distribution extras and workspace selection.

## Configuration

Settings load from environment variables and an optional `.env` in the working
directory. Keep that file untracked. Nested adapter settings use `__`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GSM_DEVICE__ADAPTER` | `simulated` | Explicit selection: `simulated` or `zte-mf833t` |
| `GSM_DEVICE__ID` | `demo-device` | Stable logical cellular device ID, independent of address or USB path |
| `GSM_DEVICE__SIMULATED_AVAILABILITY` | `ready` | `ready`, `busy`, `unavailable` or `unknown` |
| `GSM_DEVICE__ZTE_MF833T__BASE_URL` | `http://192.168.0.1` | HTTP(S) management origin; no credentials or path |
| `GSM_DEVICE__ZTE_MF833T__TIMEOUT_SECONDS` | `3` | Adapter budget for the entire model and status observation |
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

ZTE descriptors include an observation timestamp, actual model/variant and
compatibility status, independently of the selected adapter's declared model
and version. Matching device-verification evidence yields `verified`; a new
variant is `untested`; missing identity is `unknown`; another model is a
`mismatch`. Each manifest describes required transports, runtime dependencies
and compatibility evidence. See the [adapter notes](../../libs/integrations/devices/zte-mf833t/README.md).

Offline, authentication, malformed-response and adapter-timeout observations
return 200 with explicit `availability` and `issue`, and null unknown status
values. This means the query completed with an unavailable/unknown observation.
If the outer application query budget expires instead, the API returns 504.
Neither case removes declared capability support. `ready` describes the status
interface, not a guarantee of network registration or SMS delivery.

SMS and USSD operations remain queued work; this profile performs only GET
requests. For containers, route the management network to the backend; mounting
the device's installer media does not expose the HTTP interface.

Python import: `gsm_agent_server`.
