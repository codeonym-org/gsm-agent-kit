# gsm-agent-server

API transport, dependency injection and runtime composition.

The server exposes device inspection and optional durable SMS ingestion. Its hexagonal path is
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
| `GSM_INBOX__ENABLED` | `false` | Enable SQLite-backed incoming SMS polling and inbox API |
| `GSM_INBOX__DATABASE_PATH` | `data/inbox.sqlite3` | Persistent ledger; keep it across restarts |
| `GSM_INBOX__POLL_INTERVAL_SECONDS` | `5` | Delay between complete polling rounds |
| `GSM_INBOX__TIMEOUT_SECONDS` | `15` | Ingestion budget including workflow lock, scan, persistence and event dispatch |
| `GSM_DEVICE__ZTE_MF833T__INBOX_TIMEOUT_SECONDS` | `10` | Adapter scan budget including its lock, identity read and all pages |
| `GSM_DEVICE__ZTE_MF833T__PAGE_SIZE` | `50` | Rows per page, 1–500 |
| `GSM_DEVICE__ZTE_MF833T__MAX_PAGES` | `100` | Page cap; reaching it without an ending page fails the scan |
| `GSM_DEVICE__ZTE_MF833T__STORAGE_GENERATION` | `initial` | Change after replacing/resetting the device's message storage |
| `GSM_DEVICE__ZTE_MF833T__SUBSCRIPTION_GENERATION` | `initial` | Change when replacing the SIM; use an opaque local label |

Invalid adapter selections and device IDs fail configuration. Unavailable
status preserves capability support. Secrets are not included in descriptions.

## API

```bash
curl http://127.0.0.1:8000/api/adapters
curl http://127.0.0.1:8000/api/devices
curl http://127.0.0.1:8000/api/devices/demo-device
curl http://127.0.0.1:8000/api/devices/demo-device/status
```

Inspection operations use GET and CQRS queries. Unknown device IDs return 404;
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

## Incoming SMS

Install both optional integrations and enable ingestion explicitly:

```bash
GSM_DEVICE__ADAPTER=zte-mf833t GSM_DEVICE__ID=zte-device GSM_INBOX__ENABLED=true \
  uv run --package gsm-agent-server --extra zte-mf833t --extra inbox gsm-agent-server
```

Standalone distribution extras: `gsm-agent-server[zte-mf833t,inbox]` or
`gsm-agent-kit[zte-mf833t,inbox]`. Inspection alone still needs no database integration.

```bash
# Query the durable ledger; does not scan the device or alter processing state.
curl 'http://127.0.0.1:8000/api/devices/zte-device/messages?limit=50&offset=0'
# Command: trigger a full scan and commit observations, baseline and event outbox.
curl -X POST http://127.0.0.1:8000/api/devices/zte-device/inbox/ingest
```

The first successful scan baselines each storage/subscription context independently.
Existing complete and incomplete messages remain backlog; an old partial remains
backlog when completed. New partials remain ineligible until complete. Responses
include `complete`, `baselined`, `subscription_uncertain` and `replyable` flags.
`replyable` describes eligibility, not whether an event is still pending or an
automatic reply was sent. `queued` counts events newly queued by that ingestion.

Records and `SmsReceived(record_id)` events commit together before publication.
Failed publication remains pending for a later successful ingestion, including
after restart. Publication is at least once: future consumers must deduplicate
by record ID. Each scan dispatches up to 100 pending events; later rounds drain
the remainder. No AI handler or outgoing SMS submission is enabled in this slice.

The MF833T adapter uses `sms_page_data`: real hardware verification showed that
`sms_data_total` ignores the page number. Repeated, malformed, inconsistent or
failed pages fail the whole scan without committing a partial inbox or baseline.
Adapter read failures return 502, or 504 for timeouts. Unsupported capability
returns 501; a disabled inbox returns 503. Runtime logs contain device IDs and
error types, never message bodies, sender numbers or raw vendor responses.

This adapter cannot reliably identify a SIM/storage replacement. Keep the logical
device ID stable on reconnection. Update `SUBSCRIPTION_GENERATION` on a SIM change
and `STORAGE_GENERATION` on a storage reset/replacement, then restart. A new
subscription is baselined while retained device messages keep their identities
and show uncertain attribution; stale pending events are suppressed. A storage
generation change creates a new baseline and quarantines predecessor work.
Unchanged provider ID, sender, timestamp and body cannot prove that two otherwise
identical receipts are distinct; this protocol limitation remains explicit.

Run one server process/worker per physical device and ledger. In-process workflow
locks cover overlapping polls and manual ingestions; they do not coordinate
multiple owners. Shutdown cancels polling before closing adapters and SQLite.

For containers, persist the ledger and route the management network to the backend; mounting
the device's installer media does not expose the HTTP interface.

Python import: `gsm_agent_server`.
