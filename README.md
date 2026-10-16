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
and bounded plain-text preparation. AI replies, remaining integrations and browser UI are being built as
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
The application does not send replies yet. See the server README for storage
and subscription generation settings before replacing a SIM or device.

For manual SMS submission, add `--extra sms` and set
`GSM_SUBMISSIONS__ENABLED=true`. `POST /api/devices/zte-device/submissions`
accepts a client-generated UUID, international destination and text; a matching
GET returns durable progress. See the server README for the request format and
retry semantics. Sending has protocol-fixture coverage; live SMS verification is pending.

## Develop

```bash
uv sync --all-packages --all-extras
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python scripts/run_tests.py
```

`uv.lock` coordinates local development. `.v0` is excluded from workspace
membership, linting and test discovery. Select a package when working on it,
for example `uv run --package gsm-agent-core python`.

The `gsm-agent-kit` package declares installation extras: `server`, `cli`,
`zte-mf833t`, `inbox`, `sms`, `zte-http`, `serial-at`, `modemmanager`, `langchain`, and `sqlite`.
`zte-mf833t` installs the server and model-specific adapter. The server also
offers separate `simulated`, `inbox` and `sms` extras. `inbox` and `sms` install the
SQLite integration; combine them with a device profile. Other device and AI extras still select scaffold packages.
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
