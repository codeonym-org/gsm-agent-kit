# GSM Agent Kit

A toolkit for SIM-capable cellular devices and capability-based workflows,
under development.

Public source, **all rights reserved**. See [LICENSE](LICENSE) and
[third-party notices](NOTICE).

[Issue tracker](https://github.com/codeonym-org/gsm-agent-kit/issues) ·
[Project board](https://github.com/orgs/codeonym-org/projects/2) ·
[Contribution workflow](docs/github-workflow.md)

## Workspace

```text
libs/                 Independently packaged Python libraries
  core/               Domain and capability contracts
  gsm-agent/          Application workflows and CQRS
  integrations/       Cellular device, AI and storage integrations
  standard-tests/     Shared integration contract tests
  kit/                Optional installation bundles
apps/                 Server, CLI and browser UI
deploy/               Images, Compose profiles and host setup
examples/             SMS assistant and gateway examples
tests/e2e/            Assembled-system tests
.v0/                  Archived reference implementation
```

The Python workspace has 13 packages. Device inspection is implemented through
core contracts, Mediary query handlers, Dishka composition, a simulated adapter
and the model-specific ZTE MF833T HTTP adapter.
Incoming SMS ingestion is implemented with source baselines, a SQLite ledger
and durable events. Outgoing SMS submission has durable intent, per-part attempts
and bounded plain-text preparation. OpenRouter replies use a durable queue and
bounded persistent conversations. A capability-aware browser console operates these APIs.
Remaining integrations and deployment profiles are being built as
[implementation tickets](https://github.com/orgs/codeonym-org/projects/2).
Each package owns its dependencies, README, source namespace, typing marker and tests.

## Run the first slice

```bash
uv run --package gsm-agent-server --extra simulated gsm-agent-server
```

Open http://127.0.0.1:8000/docs to list adapters, inspect `demo-device` and read
its status. This profile performs no hardware access or outgoing SMS submissions.
See [server configuration and API examples](apps/server/README.md).

For the attached ZTE MF833T, select its optional integration explicitly:

```bash
GSM_DEVICE__ADAPTER=zte-mf833t GSM_DEVICE__ID=zte-device \
  uv run --package gsm-agent-server --extra zte-mf833t gsm-agent-server
```

Inspect `/api/devices/zte-device` and `/api/devices/zte-device/status`. This
profile reads model, firmware, hardware revision and network status. The host needs network access to the
management interface, which defaults to `http://192.168.0.1`.

To enable durable incoming SMS polling:

```bash
GSM_DEVICE__ADAPTER=zte-mf833t GSM_DEVICE__ID=zte-device GSM_INBOX__ENABLED=true \
  uv run --package gsm-agent-server --extra zte-mf833t --extra inbox gsm-agent-server
```

Read `/api/devices/zte-device/messages`. The first scan records the existing
inbox as backlog; later complete messages become eligible for processing.
Auto-reply is disabled by default. See the server README for storage
and subscription generation settings before replacing a SIM or device.

For manual SMS submission, add `--extra sms` and set
`GSM_SUBMISSIONS__ENABLED=true`. `POST /api/devices/zte-device/submissions`
accepts a client-generated UUID, international destination and text; a matching
GET returns durable progress. See the server README for the request format and
retry semantics. Sending has protocol-fixture coverage; live SMS verification is pending.

For OpenRouter replies, add `--extra ai`, enable `GSM_ASSISTANT__ENABLED=true`
and configure `GSM_ASSISTANT__API_KEY` in your local environment. The assistant
starts in dry-run mode. See the [assistant setup](apps/server/README.md#sms-assistant)
for live sending, conversation retention, budgets and operator status.

## Operator console

The [browser console](apps/web/README.md) selects a logical device and displays
capabilities, observed status, inbox, assistant mode and submission progress.
With the backend running, use `pnpm install --frozen-lockfile` and `pnpm web:dev`
from the repository root, then open http://127.0.0.1:5173. It uses the existing
API and offers SMS/balance actions only when the adapter implements them.
pnpm is pinned in root `package.json`; no provider credentials go in the UI.

## Develop

```bash
uv sync --all-packages --all-extras
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python scripts/run_tests.py
pnpm install --frozen-lockfile
pnpm web:generate-api
pnpm web:check
pnpm web:build
pnpm web:test
```

`uv.lock` coordinates local development. `.v0` is excluded from workspace
membership, linting and test discovery. Select a package when working on it,
for example `uv run --package gsm-agent-core python`.

The `gsm-agent-kit` package declares installation extras: `server`, `cli`,
`zte-mf833t`, `inbox`, `sms`, `ai`, `zte-http`, `serial-at`, `modemmanager`, `langchain`, and `sqlite`.
`zte-mf833t` installs the server and model-specific adapter. The server also
offers separate `simulated`, `inbox`, `sms` and `ai` extras. `inbox` and `sms` install the
SQLite integration; `ai` adds SQLite and LangChain/OpenRouter. Combine them with a device profile.
Other device integrations still select scaffold packages.
No packages or images have been published.

See [the proposed monorepo layout](docs/monorepo-layout.md) for the planned
libraries, integrations, applications, and deployment structure.

The [domain glossary](GLOSSARY.md) defines the shared terminology. The
[cellular device interface proposal](docs/design/cellular-device-interface.md) applies that language
to capability contracts and records scenarios the new implementation must handle.

The original working draft is preserved in [`.v0/`](.v0/README.md) as a reference
for the new implementation. Its source, tests, scripts, dependency metadata,
device investigations, and local configuration/data were archived together.
The archived virtual environment may contain paths from its previous location;
recreate it before attempting to run the draft from `.v0`.

Keep `.v0` until the replacement covers the required behavior. It can then be
removed explicitly. Local secrets, databases, and environments remain ignored.
