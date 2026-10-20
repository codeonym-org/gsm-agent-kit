# SMS assistant containers

Run commands from the repository root. Docker Engine with Compose v2.24+ (or
Compose v5) is required. The deployment consists of one backend process and a
named volume containing its three SQLite databases. The production console
overlay adds the built SPA and tRPC gateway. For local UI development, use
`pnpm web:dev` against the published backend port instead.

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

The backend now enforces exclusive ownership of each enabled SQLite ledger in
the shared local state volume before device access, migration/recovery or
worker startup. A second container sharing any ledger refuses startup. Native
OS locks release automatically on shutdown or process death; `.owner.lock`
sidecars intentionally remain and must not be deleted to bypass a conflict.
Restore the volume with the same backend UID/GID so it can reopen those files.
Separate volumes, hard-link aliases, network filesystems and unrelated software
are outside this guard; the single physical-device owner rule still applies.
See [state ownership](../../apps/server/README.md#persistent-state-ownership).

## Production console

Add the console overlay to the ZTE profile. Both files belong to the same
`gsm-agent-kit` project and reuse its existing state volume. Add an optional
`GSM_CONSOLE_PORT=8080` setting to root `.env` to choose the browser port; provider
keys and the assistant's dry-run setting remain in that same file.

```bash
docker compose --env-file .env \
  -f deploy/compose/zte-mf833t.yaml -f deploy/compose/console.yaml \
  --profile zte --profile console up --build -d --wait
```

Open http://127.0.0.1:8080 (or your configured port), then enter your API token
using **API connection**. No Vite or host-side Node/pnpm process is needed.
The gateway listens on port 3001 **inside** the Compose network and has no
published host port; a host Grafana on 3001 does not conflict. The backend's
existing loopback port 8000 remains available for API tools. Browser requests
use only the console origin:

```text
browser :8080 → Caddy → static SPA/assets
                     → /api, /health → zte:8000
                     → /trpc (WebSocket) → realtime:3001 → zte:8000/api/events
```

Only the backend receives the provider credentials from `.env`. The console and
gateway receive their internal upstream addresses; they do not receive an API
token granting elevated access. HTTP authorization and the browser's WebSocket
connection token pass through to the existing backend checks. The proxy preserves
Host/Origin, keeps API failures out of SPA fallback, does not cache API responses
and does not enable retries for submission POSTs. Hashed assets use immutable
caching; SPA HTML requires revalidation.

```bash
curl http://127.0.0.1:8080/_console/health
curl http://127.0.0.1:8080/health
docker compose --env-file .env \
  -f deploy/compose/zte-mf833t.yaml -f deploy/compose/console.yaml \
  --profile zte --profile console ps
```

`/_console/health` checks static hosting, `/health` checks Python through the
proxy, and the gateway container's health check checks its process. These do not
prove that a SIM or carrier is ready; inspect device status and assistant jobs
in the UI. Both new containers are non-root with read-only filesystems and no
device mounts. Production Node runs a bundled gateway, and Caddy serves the
built SPA; development dependencies are absent from the runtime images.

Stop the application while retaining its state:

```bash
docker compose --env-file .env \
  -f deploy/compose/zte-mf833t.yaml -f deploy/compose/console.yaml \
  --profile zte --profile console down
```

This is a loopback HTTP deployment. Configure an authenticated TLS reverse proxy
before exposing it to other machines, preserve the public Host/Origin through
that proxy, and keep internal gateway/backend ports private. Automatic public
HTTPS and domain provisioning are not configured by this profile. Existing
single-owner device and dry-run/manual-send rules still apply.

## Hardware-free smoke test

```bash
python scripts/smoke_containers.py
```

This builds the backend, fixture, console and gateway targets and creates a uniquely named disposable Compose
project, with an internal network, no published ports, synthetic credentials
and dedicated volumes. It never loads the root `.env`. The production target
is checked for its selected dependencies, non-root user and absence of fixture
code. The smoke backend runs the production API, Mediary workflows, background
workers, SQLite stores and real ZTE HTTP adapter. Its test-only `AIAgent` adapter
calls a separate deterministic fixture service; OpenRouter/LangChain and real
carrier services are not called. The fixture service also emulates the ZTE HTTP
protocol. This establishes protocol behavior, not firmware compatibility.

The checks first verify the production SPA's deep links, asset types/caching,
notices and JSON API authorization/errors. They exercise a same-origin tRPC
subscription through Caddy and the bundled gateway to Python, reject wrong-token
and cross-origin WebSocket clients, then perform the SMS checks through Caddy's
API proxy. The checks establish the empty inbox baseline, inject an incoming message,
observe one normalized accepted reply, verify a competing backend cannot acquire
the shared state volume, recreate the backend and fixture
containers, verify durable inbox/jobs/submissions, send a second message with
restored conversation history, switch to dry-run, and verify generation without
another automatic submission. A final authenticated manual POST through the
proxy verifies plain-text preparation and replay of the same request UUID without
another device submission. Repeated polling must not generate duplicates. The script
removes only its own containers, network and synthetic volumes, including on
failure. Built images and build cache remain reusable. Use `--no-build` after a
successful build when no image inputs changed. CI runs this same smoke test.

The fixture controls are isolated in the `smoke` target and Compose file. They
are absent from the production image. Do not deploy the smoke target publicly.
