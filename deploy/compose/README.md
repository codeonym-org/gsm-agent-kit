# SMS assistant containers

Run commands from the repository root. Docker Engine with Compose v2.24+ (or
Compose v5) is required. The deployment consists of one backend process and a
named volume containing its three SQLite databases. The browser and its tRPC
gateway remain separate; use `pnpm web:dev` against the published backend port.

## ZTE MF833T

The host must already expose the device's HTTP management network. Read the
[host prerequisites](../host/README.md) before starting. Stop any existing local
backend that owns this device or uses port 8000.

Keep the following settings in the root `.env`, alongside the other
[server settings](../../apps/server/README.md). Do not overwrite an existing
file or commit its values:

```dotenv
GSM_DEVICE__ID=zte-device
GSM_DEVICE__ZTE_MF833T__BASE_URL=http://192.168.0.1
GSM_API_TOKEN=replace-with-your-local-token
GSM_ASSISTANT__API_KEY=replace-with-your-openrouter-key
GSM_ASSISTANT__MODEL=openai/gpt-4.1-mini
GSM_ASSISTANT__DRY_RUN=true
GSM_CONTAINER_PORT=8000
```

```bash
docker compose --env-file .env -f deploy/compose/zte-mf833t.yaml --profile zte up --build -d --wait
docker compose --env-file .env -f deploy/compose/zte-mf833t.yaml --profile zte ps
```

The service reads `.env` at runtime, enables inbox ingestion, durable submissions
and the assistant, selects `zte-mf833t`, and fixes all database paths under
`/var/lib/gsm-agent`. Environment variables set by the Compose file take
precedence over `env_file`; other server settings are passed through. The
OpenRouter key is required even in dry-run, which still generates replies using
paid AI. `GSM_ASSISTANT__DRY_RUN` defaults to true; an existing explicit false
in `.env` enables actual replies. API/provider credentials never enter a build
argument, image layer or browser bundle. Runtime environment values remain
visible to users with Docker administrative access; restrict host access.

The API is published only on `127.0.0.1:8000` by default. `/docs` describes it.
`GET /health` is an unauthenticated process/lifespan health check: it reports
`adapter_profile`, but does not prove network registration, an available SIM,
worker progress or successful AI/device I/O. With your bearer token, inspect
`GET /api/devices/zte-device/status` and
`GET /api/devices/zte-device/assistant` for device availability, assistant mode
and job counts; `/assistant/jobs` reports individual failures. Substitute your
configured logical device ID when it differs. Logs omit SMS bodies and provider
exception details. ZTE balance consultation remains unsupported (501).

Dry-run prevents **automatic** SMS submission. The enabled manual submission API
can still send real SMS; protect the API token. The initial inbox scan baselines
existing messages; only later eligible messages receive replies. Setting
`GSM_ASSISTANT__DRY_RUN=false` and rerunning `up -d --wait` enables live replies.
Sending has protocol-fixture coverage; this profile does not add live carrier
verification or delivery receipts.

```bash
docker compose --env-file .env -f deploy/compose/zte-mf833t.yaml --profile zte logs --tail 50 zte
docker compose --env-file .env -f deploy/compose/zte-mf833t.yaml --profile zte restart zte
docker compose --env-file .env -f deploy/compose/zte-mf833t.yaml --profile zte down
```

Restart/recreation/`down` preserve the `gsm-agent-kit_zte-state` volume. Do not
use `down --volumes` unless intentionally deleting inbox, submission and
conversation history. Back up the complete volume with the service stopped,
including SQLite WAL files if present; restore with UID/GID 10001 ownership.
Container storage is separate from local `data/` and is not migrated implicitly.
Keep a stable logical ID and generation settings across restarts. Before
replacing a SIM or its storage, update the server's subscription/storage
generation settings to avoid mixing identity and conversation history.

The image runs as UID/GID 10001, with a read-only root filesystem, a writable
state volume and temporary `/tmp`. It has no device/media mounts, Docker socket,
host D-Bus access, added capabilities or privileged mode. The default bridge
needs outbound access to the device management address and OpenRouter. Exactly
one backend owns a physical device and its state: do not scale this service or
run another application against that device concurrently.

## Hardware-free smoke test

```bash
python scripts/smoke_containers.py
```

This builds both image targets and creates a uniquely named disposable Compose
project, with an internal network, no published ports, synthetic credentials
and dedicated volumes. It never loads the root `.env`. The production target
is checked for its selected dependencies, non-root user and absence of fixture
code. The smoke backend runs the production API, Mediary workflows, background
workers, SQLite stores and real ZTE HTTP adapter. Its test-only `AIAgent` adapter
calls a separate deterministic fixture service; OpenRouter/LangChain and real
carrier services are not called. The fixture service also emulates the ZTE HTTP
protocol. This establishes protocol behavior, not firmware compatibility.

The checks establish the empty inbox baseline, inject an incoming message,
observe one normalized accepted reply, recreate the backend and fixture
containers, verify durable inbox/jobs/submissions, send a second message with
restored conversation history, switch to dry-run, and verify generation without
another submission. Repeated polling must not generate duplicates. The script
removes only its own containers, network and synthetic volumes, including on
failure. Built images and build cache remain reusable. Use `--no-build` after a
successful build when no image inputs changed. CI runs this same smoke test.

The fixture controls are isolated in the `smoke` target and Compose file. They
are absent from the production image. Do not deploy the smoke target publicly.
