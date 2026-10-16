# gsm-agent-server

API transport, dependency injection and runtime composition.

The server exposes device inspection, optional durable SMS ingestion/submission
and OpenRouter replies with persistent conversations. Its hexagonal path is
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
the remainder. Inbox polling does not itself send SMS or run an AI handler.

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

## Outgoing SMS

```bash
GSM_DEVICE__ADAPTER=zte-mf833t GSM_DEVICE__ID=zte-device GSM_SUBMISSIONS__ENABLED=true \
  uv run --package gsm-agent-server --extra zte-mf833t --extra sms gsm-agent-server
```

Standalone extras: `gsm-agent-server[zte-mf833t,sms]` or
`gsm-agent-kit[zte-mf833t,sms]`. Add `inbox` and enable it separately to receive
messages in the same process. Both SQLite ledgers need persistent storage.

Submit with `POST /api/devices/zte-device/submissions`:

```json
{
  "request_id": "c3ba616b-a7b1-4515-924a-b2b6d03527af",
  "destination": "+<country-code><number>",
  "text": "Hello from GSM Agent Kit"
}
```

Replace the destination placeholder with an international number. Generate a new
UUID for each new intent and keep that exact UUID, destination and text for
retries. Reusing an ID with different input returns 409. Consult progress using
`GET /api/devices/zte-device/submissions/{request_id}`; that query performs no device I/O.

Responses contain the immutable prepared parts, truncation flag, accepted-part
count and each attempt's identity, outcome and reason. HTTP 200 reports durable
progress, including rejected/unknown outcomes; `complete` means all parts were
accepted for sending, never recipient delivery. Unknown/rejected parts stop the
request. A replay can resume pending or known-not-submitted parts, but never
accepted or uncertain ones. The original plan remains unchanged after a settings change.

Intent and each attempt commit before device I/O. Startup marks interrupted
attempts unknown without sending anything. An unresolved unknown attempt blocks
new requests on that logical device until separately reconciled; there is no
force-retry endpoint. Keep the physical device/SIM and both ledgers consistent
while requests are unresolved. Run one runtime owner per device/ledger.
Cancellation quarantines only the lock owner's active attempt. Application
deadlines return existing durable progress, or 504 if no intent was committed.

Markdown styles and HTML are removed by application policy; links/code text are
preserved. Paragraph, sentence and word boundaries are preferred, with grapheme
boundaries for long words. Parts are independent single-segment SMS messages,
numbered `(1/2)`, rather than concatenated SMS with UDH. GSM7 extension characters
cost two units; the current adapter supports GSM7 and BMP UCS2. Non-BMP text,
surrogates, empty text and unrepresentable clusters return 422 before intent/I/O.
Output caps include numbering; shortening is visible as `truncated=true` and `...`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GSM_SUBMISSIONS__ENABLED` | `false` | Enable durable manual sending; disabled returns 503 |
| `GSM_SUBMISSIONS__DATABASE_PATH` | `data/submissions.sqlite3` | Persist intent, plans and attempts |
| `GSM_SUBMISSIONS__MAX_TOTAL_CHARS` | `240` | Total transmitted characters, including numbering; 16–10000 |
| `GSM_SUBMISSIONS__MAX_PARTS` | `3` | Maximum independent SMS parts, 1–9 |
| `GSM_SUBMISSIONS__TIMEOUT_SECONDS` | `100` | Whole command budget, including workflow lock and persistence |
| `GSM_DEVICE__ZTE_MF833T__SEND_TIMEOUT_SECONDS` | `30` | Per-part adapter budget, including operation lock, checks, POST and completion polling |
| `GSM_DEVICE__ZTE_MF833T__SEND_POLL_INTERVAL_SECONDS` | `1` | Delay between completion checks |

The ZTE adapter checks model identity before writing and waits for asynchronous
firmware completion after its initial HTTP acknowledgement. Sending is covered
by fake HTTP and SQLite/API tests; no live test SMS has been sent for this slice.
Its new sending capability therefore has fixture evidence only, and overall
variant compatibility is `untested` until all declared capabilities have device verification.

## SMS assistant

Install the assistant profile and start in dry-run mode:

```bash
GSM_DEVICE__ADAPTER=zte-mf833t GSM_DEVICE__ID=zte-device \
  GSM_INBOX__ENABLED=true GSM_ASSISTANT__ENABLED=true \
  uv run --package gsm-agent-server --extra zte-mf833t --extra inbox --extra ai gsm-agent-server
```

Set `GSM_ASSISTANT__API_KEY` in your local `.env` or environment before running.
It must be an OpenRouter key. Set `GSM_ASSISTANT__MODEL` to your selected
tool-calling model; the default is `openai/gpt-4.1-mini` through OpenRouter.
The archived `.v0` settings are not read automatically. The example
[environment file](../../examples/sms-assistant/.env.example) contains all settings.
Standalone installation: `gsm-agent-kit[zte-mf833t,inbox,sms,ai]`.

Dry-run calls the configured model and prepares a bounded preview in local
workflow storage, without submitting SMS. To send replies, add `--extra sms`,
set `GSM_SUBMISSIONS__ENABLED=true` and `GSM_ASSISTANT__DRY_RUN=false`, then restart.
The same SMS budgets and encoding rules apply to manual and generated replies.
No credentials or paid calls are needed to run tests.

Operator queries, protected by `GSM_API_TOKEN` when configured:

- `GET /api/devices/zte-device/assistant`: auto-reply/dry-run flags and job counts.
- `GET /api/devices/zte-device/assistant/jobs?limit=50&offset=0`: newest jobs with
  incoming record ID, submission request UUID, state, issue code and time.
- `GET /api/devices/zte-device/submissions/{request_id}`: exact submitted parts
  and acceptance evidence. Dry-run/ignored jobs have no submission record.

Jobs move through queued, generating, prepared and submitting to completed,
ignored, dry_run, failed or interrupted. Completed means every part was accepted
for submission; delivery is not established. Failures are visible in job state,
without provider payloads, SMS text, phone numbers or secrets in default logs.
Status/job queries perform no device or model I/O. Default logs omit message
content; external framework tracing, if explicitly enabled, has its own data policy.

Incoming events commit a deduplicated job before acknowledgement. A separate
worker generates replies, so the model's deadline cannot block an inbox scan.
Fresh complete messages after the initial baseline are eligible. Messages
ingested while auto-reply is disabled are not replayed when it is enabled.
Prepared jobs resume after restart. Interrupted model generation becomes failed;
provider errors are not automatically retried. A submitting job is reconciled
from the submission ledger without resending. An uncertain or incomplete reply
becomes interrupted; this first slice has no force-retry endpoint.
Dry-run/ignored/failed jobs remain terminal if configuration changes later.

Conversation identity combines logical device, storage generation, subscription
generation and normalized international correspondent. `00` and international
phone formats normalize to E.164. National numbers require an explicit
`DEFAULT_REGION` (for example `MA`); named senders, short codes and unsupported
addresses do not trigger model calls or replies. Update device generation
settings when changing SIM/storage as described above. Attribution is checked
again after model generation, before submission.

History persists in a third database. It includes capped user input and exact
reply parts backed by acceptance evidence, including only accepted parts of an
interrupted multi-part reply. Dry-run previews and ignored outputs do not enter
conversation history. Retention deletes oldest whole exchanges at startup and
on history read/completion, by age, message count and character count. An exchange
larger than the budget is omitted. The current input has a separate character cap.
Minimal job tombstones remain for deduplication, and inbox/submission audit
ledgers have independent retention. Persist all databases and run one worker
process per device/ledger; there is no distributed lease.

The agent has no live browsing/news tools. Its prompt requires an honest
limitation response to such questions and plain text for every human answer.
Model output is still checked by application SMS normalization and caps.

| Variable | Default | Meaning |
| --- | --- | --- |
| `GSM_ASSISTANT__ENABLED` | `false` | Queue and process replies to fresh incoming events |
| `GSM_ASSISTANT__DRY_RUN` | `true` | Generate/prepare previews without SMS submission |
| `GSM_ASSISTANT__DATABASE_PATH` | `data/conversations.sqlite3` | Durable jobs and bounded conversation history |
| `GSM_ASSISTANT__API_KEY` | unset | OpenRouter key; required when enabled |
| `GSM_ASSISTANT__MODEL` | `openai/gpt-4.1-mini` | OpenRouter model ID supporting tool calling |
| `GSM_ASSISTANT__INSTRUCTIONS` | general SMS assistant | Configurable instructions plus fixed SMS constraints |
| `GSM_ASSISTANT__MAX_OUTPUT_TOKENS` | `384` | Model output cap, including structured-output overhead |
| `GSM_ASSISTANT__TIMEOUT_SECONDS` | `60` | Whole model invocation deadline |
| `GSM_ASSISTANT__POLL_INTERVAL_SECONDS` | `2` | Delay between processing one reply job and the next |
| `GSM_ASSISTANT__DEFAULT_REGION` | unset | Explicit ISO country code for national sender numbers |
| `GSM_ASSISTANT__HISTORY_MAX_MESSAGES` | `20` | Retained user and assistant messages per conversation |
| `GSM_ASSISTANT__HISTORY_MAX_CHARS` | `6000` | Retained text characters per conversation |
| `GSM_ASSISTANT__HISTORY_RETENTION_DAYS` | `30` | Maximum age of retained exchanges |
| `GSM_ASSISTANT__INPUT_MAX_CHARS` | `2000` | Maximum current user input sent to the model |

Python import: `gsm_agent_server`.
