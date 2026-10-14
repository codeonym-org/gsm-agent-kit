# GSM Agent Kit

The proposed library, integration, application, and deployment layout is recorded
in [the monorepo layout document](../docs/monorepo-layout.md).

A first draft SMS assistant for the attached **inwi ZTE MF833T**, using its
local HTTP API. It polls incoming SMS, stores processing state in SQLite, and
uses LangChain's `create_agent` with `ChatOpenRouter` to generate a structured reply decision.
Mediary handles commands, queries, stream queries, and application events;
Dishka composes the adapters and handlers.

## Run

```bash
uv sync
cp .env.example .env
uv run python main.py
```

The API listens on `127.0.0.1:8000`; interactive docs are at
http://127.0.0.1:8000/docs. Use **one worker and one instance per modem**.
The database has a process lock so a second worker using the same database
fails on startup instead of interfering with message recovery.

Defaults receive/store SMS but do not run AI or send replies. The first
successful inbox scan baselines existing messages without answering them.
Wait for that scan before sending a new test SMS.

To generate replies for **new** incoming messages, configure `.env`:

```dotenv
GSM_AGENT__API_KEY=your-key
GSM_AGENT__MODEL=openai/gpt-4.1-mini
GSM_LISTENER__AUTO_REPLY=true
GSM_LISTENER__DRY_RUN=true
```

Use an **OpenRouter API key**. `OPENROUTER_API_KEY` exported in the shell also works.
Model IDs use OpenRouter's `provider/model` format. The model, system prompt,
and optional provider base URL are configurable. Restart after settings changes.
Dry-run still calls the model and stores the reply; it does not transmit SMS.
Inspect `/api/messages` for `dry_run` records and their generated replies.
Set `GSM_LISTENER__DRY_RUN=false` and restart to send replies for subsequent
messages. Existing baselined, observed, or dry-run records are not replayed.

## Conversation memory and reply budgets

The listener now persists conversation history in SQLite using the sender's
normalized phone number as `thread_id`. Spaces are removed and international
`00` prefixes become `+`; country codes are not inferred for local numbers.
Threads stay separate and survive restarts. Application-owned memory is replayed
through the framework-independent `AIAgent` port; it does not rely on LangChain
checkpoints. The manual invoke/stream endpoints still use the history supplied
in their request and do not mutate the listener's phone threads.

Incoming messages and confirmed outgoing text enter history. Dry-run replies
and unconfirmed send parts do not. Baseline SMS are excluded; older confirmed
`sent` records are imported when upgrading an existing database. Retry inputs
stop at the original user turn, so they cannot accidentally answer a later SMS.

```dotenv
GSM_AGENT__MAX_REPLY_CHARS=240
GSM_AGENT__MAX_SMS_PARTS=3
GSM_AGENT__MAX_OUTPUT_TOKENS=384
GSM_AGENT__HISTORY_MESSAGES=20
GSM_AGENT__HISTORY_CHARS=6000
```

The character limit bounds normalized reply payload; SMS count is a separate
hard limit that includes transport numbering. The token limit bounds each model
completion (including structured-output overhead), not the entire request's
retry/agent-loop token usage. History bounds limit what is replayed to the model,
not what is retained in SQLite. Restart after changing settings; existing `.env`
files need not be replaced because these defaults apply automatically.

The system prompt always instructs the assistant to **never generate Markdown**.
A second pass parses Markdown into plain text, removes styling, retains readable
code and link destinations, and normalizes whitespace and typographic quotes/
dashes. Unsupported emoji and invisible formatting characters are removed.
The final invoke/stream result and actual outbound SMS use this normalized text;
streamed text previews can still contain model-generated formatting.

The SMS planner prefers paragraph breaks, sentence endings, then word boundaries.
Only tokens longer than one segment require a hard cut. Multi-message replies
are numbered `(1/2)`, `(2/2)`, etc.; numbering is included in segment budgets.
Each part is sent as an independent single-segment SMS, in sequence, rather than
leaving arbitrary splitting to the modem. GSM-7 text has a 160-unit budget (some
extension characters cost two units); Unicode, including Arabic, has 70 units.
These are the [standard single-segment capacities](https://www.twilio.com/docs/glossary/what-sms-character-limit).
The modem adapter selects GSM-7 or Unicode for each prepared part.

If a model overshoots either reply budget, the planner trims at a natural break
and adds `...`. Once the configured SMS maximum is reached, no further parts are
sent. `/api/messages` exposes `reply_parts` and `sent_parts`, so you can inspect
the prepared payload and confirmed progress. `POST /api/sms` applies the same
normalization/budgets and reports the planned part count in its receipt.

To check the modem without starting the listener or printing private SMS:

```bash
uv run python scripts/probe_modem.py
```

## HTTP API

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Process health and configured listener/reply mode |
| `GET /api/modem/status` | Live modem network and unread count |
| `GET /api/modem/balance` | Consult SIM balance using one configured USSD request |
| `GET /api/messages?limit=50` | Stored messages, states, generated replies, error types |
| `POST /api/sms` | Send `{ "recipient": "+212…", "text": "Hello" }`; respects dry-run |
| `POST /api/agent/invoke` | Generate a decision without sending SMS |
| `POST /api/agent/stream` | Stream text previews and final structured result as SSE |

The agent endpoints accept a caller-supplied conversation:

```json
{"messages": [{"role": "user", "content": "Bonjour!"}]}
```

Invoke returns `{ "action": "reply", "text": "…" }` or an `ignore` decision.
Decisions also include `ignore_reason` (null for replies). Only explicit `spam`
or `automated_notification` decisions are allowed to remain silent. Unexplained
ignores and lack of available information produce a short fallback reply.
The assistant has no live news/search tool: it should explain that limitation
when asked for current news rather than fabricate headlines or ignore the SMS.
Processing logs include message keys, ignore reasons, and generation/send states,
without SMS content, recipient numbers, or credentials.
Streaming produces `text` events when the model emits text, exactly one `result`
event on success, or an `error` event on failure. Text fragments may represent
structured-output previews; only the final validated result is usable as a reply.
Some models produce a final result without text fragments.

```bash
curl -N http://127.0.0.1:8000/api/agent/stream \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Bonjour!"}]}'
```

If `GSM_API_TOKEN` is set, all `/api` endpoints require
`Authorization: Bearer <token>`. `/health` and API documentation remain public.
Manual sends wait for modem completion; an uncertain outcome returns HTTP 503
with `send_outcome: "uncertain"`. Do not blindly repeat such requests.
The manual send API does not provide a durable outbox or idempotency key yet.

### Balance (solde)

```bash
curl http://127.0.0.1:8000/api/modem/balance
```

Add the same Bearer authorization header if `GSM_API_TOKEN` is configured.
The response contains `code`, the carrier's `text`, UTC `checked_at`, and
`session_open` (whether the response indicated an interactive menu before
cleanup). It does not infer a currency amount or confuse recharge credit,
bonus credit, and data quotas. The consultation is performed even in SMS dry-run
mode: it sends USSD, not SMS. No model is called.

The default is `*120*30#`, published on
[Inwi's balance consultation page](https://inwi.ma/fr/consultationsolde).
[Inwi's recharge page](https://inwi.ma/fr/particuliers/recharges) also lists
`*120*20#`; configure the code appropriate for your SIM/offer:

```dotenv
GSM_MODEM__BALANCE_CODE="*120*30#"
GSM_MODEM__USSD_TIMEOUT=30
```

Balance consultation is a Mediary query dispatched through `QuerySender`;
the adapter's USSD transport does not make it an application command.
The previous POST route remains as a compatibility alias, hidden from OpenAPI.
Commands ingest incoming SMS and send outgoing SMS; those operations change application state.

The endpoint checks for a stale pending session and attempts bounded cancellation
before submitting another consultation. If cancellation cannot complete, it returns
HTTP 502 explaining that modem USSD is stuck; no new consultation is submitted.
Otherwise it starts one consultation, waits for the modem's response, and
cancels the USSD session afterward. It never selects menu options or automatically
retries a consultation. It serializes with other consultations and SMS sends.
Timeouts return HTTP 504; unsupported USSD, carrier errors, and malformed modem
responses return HTTP 502. LTE firmware/network support must be verified live.

## Layers

```text
src/gsm_agent/
  api/           FastAPI routes, request schemas, SSE transport
  application/   Mediary commands, queries, event handlers, ports
  domain/        SMS entities, reply decisions, states, policies, errors
  infra/         ZTE HTTP, LangChain agent, SQLite adapters
  di/            Dishka providers and composition root
  runtime/       Environment settings, listener lifecycle, tracing setup
  webapp.py      App factory connecting DI, transport, and runtime
```

The original top-level skeleton is migrated into this package. Domain code
uses the standard library; application code depends on ports and Mediary.
LangChain, HTTP, SQLite, and FastAPI objects do not appear in the AI port.
`AIAgent.invoke` returns a `ReplyDecision`; `AIAgent.stream` yields
`AgentStreamEvent` values and finishes with a validated decision. Replacing
LangChain means implementing this protocol and changing its DI provider.

Incoming processing is `PollInbox` → durable inbox → `SmsReceived` →
`ReplyToSms` → phone-thread history → `AIAgent` → normalized segment plan → `SendSmsPart`.
Polling and all handlers use scoped Mediary instances from Dishka.
The poller retries connection failures with bounded backoff, independently
of limited AI generation retries. Completed multipart messages are required
before generation. Invalid or incomplete API snapshots are not baselined.

Mediary's OpenTelemetry behavior wraps dispatch. Set `GSM_TRACE_CONSOLE=true`
for console spans; otherwise it uses the global OpenTelemetry provider, which
can be configured by a deployment. SMS bodies are not logged by our listener.

## Delivery and scope

- SQLite records identify messages by modem ID, sender, timestamp, and content;
  unread flags are not the processing ledger. Completed versions of messages
  present at baseline do not trigger replies.
- The reply is stored before sending. Startup recovers interrupted generation
  to `pending`; interrupted sends become `uncertain` and are not retried.
  Each confirmed part and its delivered conversation text are committed together.
  If a later part fails, confirmed progress is preserved; the whole reply is not retried.
  Exactly-once delivery cannot be guaranteed by this modem protocol.
- An acknowledged send is followed by `sms_cmd_status_info` completion checks.
  A `sent` record means modem completion, not a carrier delivery receipt.
- There are no external webhooks, agent tools, automatic deletion, or retention
  jobs yet. Device storage is limited; messages remain on the modem.
- Outgoing messages use GSM-7 where possible and Unicode otherwise. The formatter
  removes non-BMP characters (such as many emoji) because this firmware's encoding
  differs. Each prepared part is one physical SMS segment; live sending with both
  encodings still needs end-to-end validation.
- Authentication/session renewal for modem firmware requiring a login is not
  implemented. Reads worked without an explicit login on the inspected device.
- Physical SMS sending and live OpenRouter responses require end-to-end validation.
  Tests use fake services and never send SMS or make paid model calls.

See [device investigation](docs/modem-capabilities.md) for local firmware evidence.
Framework references: [Mediary](https://pypi.org/project/mediary/0.4.0/),
[LangChain agents](https://docs.langchain.com/oss/python/langchain/agents), and
[structured output](https://docs.langchain.com/oss/python/langchain/structured-output), and
[ChatOpenRouter](https://reference.langchain.com/python/langchain-openrouter/chat_models/ChatOpenRouter).

## Development

```bash
uv run pytest -q
uv run ruff check src tests scripts main.py
uv run ruff format --check src tests scripts main.py
```

Tests cover the real LangChain agent graph using a fake tool-calling model,
Mediary/Dishka processing, HTTP and SSE transport, Markdown normalization, SMS
budgets and natural splits, Arabic/GSM-7 encoding, pagination, phone-thread
isolation, memory persistence, database upgrades, partial sends, deduplication,
generation retries, and restart recovery.
