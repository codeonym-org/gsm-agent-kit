# GSM Agent Kit operator console

A routed React/TypeScript SPA using shadcn/ui, Radix, Tailwind CSS and Lucide.
The TypeScript tRPC gateway delivers live notifications over WebSockets. Python
retains the application handlers, durable state, device ownership and SMS policy.
JavaScript uses the root pnpm workspace; Python uses uv.

## Run locally

Use Node 24+ and the pinned pnpm 11.26.0. From the repository root:

```bash
pnpm install --frozen-lockfile
pnpm web:dev
```

This starts Vite on http://127.0.0.1:5173 and the realtime gateway on loopback
port 3001. Keep the [Python backend](../server/README.md) running on port 8000 in
another terminal. Restart both after backend transport changes. For the ZTE profile:

```bash
uv run --package gsm-agent-server --extra zte-mf833t --extra inbox --extra sms --extra ai gsm-agent-server
```

Server and web proxy configuration live in the repository-root `.env`. Optional
web settings (defaults shown) are server-side only:

```dotenv
GSM_API_PROXY_TARGET=http://127.0.0.1:8000
GSM_REALTIME_PORT=3001
GSM_REALTIME_PROXY_TARGET=http://127.0.0.1:3001
```

Environment variables override the file. Changing the gateway port also requires
updating its proxy target. Provider credentials must never use `VITE_` variables.
Use **API connection** to enter the backend's API token when required. It stays
in memory, never in browser storage, URLs or generated assets. Reloading requires
connecting again. The gateway forwards that token; it does not substitute a
privileged server credential.

## Screens and operations

- **Overview:** network observations, signal, assistant policy, recent messages,
  adapter summary and balance support. Counts and observations come from the API.
- **Inbox:** paginated messages, sender/body search within the current page,
  message details and explicit incomplete/baseline/uncertain attribution states.
  Incoming text renders as text, never executable HTML or Markdown.
- **Reply jobs:** live workflow states, submission details and request UUID lookup.
- **Device & capabilities:** logical identity, adapter build, hardware/firmware,
  verification metadata and declared capabilities. Support differs from availability.
- **Compose SMS:** manual submission in a focused dialog. One UUID is allocated
  before POST; progress reads never resend. Acceptance is distinct from delivery.
  Keep the UUID before closing the dialog or leaving/reloading. Find submission
  progress in Reply jobs reopens the durable record. Drafts are not persisted in
  the browser. Manual sending is independent of the automatic assistant's dry run.
- Balance consultation is explicit and capability-gated. Live updates and refresh
  never call balance/USSD. The current ZTE adapter declares it unsupported.

## Realtime design

```text
Committed inbox/reply/submission changes
  → Python ChangeFeed (/api/events)
  → tRPC gateway (changes subscription)
  → browser WebSocket (/trpc)
  → invalidation of typed HTTP read views
```

Infra decorators publish only after store operations commit successfully. The
feed contains revisions, not phone numbers, message bodies or credentials. Each
subscriber has a bounded one-entry queue: slow clients coalesce invalidations.
Initial connection and every reconnect invalidate current views, so missed
notifications recover by reading durable state. This is an invalidation feed,
not a durable event log or command transport.

The gateway reconnects to Python on transient failures; tRPC reconnects the
browser to the gateway. The header shows live, connecting, reconnecting or denied
access. Updates are coalesced over 80ms. Inbox/jobs do not use timed browser
polling. Hardware status and configured-device observations refresh every 30s
because these adapters do not provide push status; **Refresh** is also available.

The feed is process-local and follows the existing single-owner device/SQLite
runtime. Run one Python owner. Multiple independent API workers would require a
shared change transport and coordinated device ownership.

The gateway validates backend authorization and same-origin browser upgrades,
uses heartbeat detection and bounds frame sizes. Tokens travel in connection
frames, not query strings. Domain/application packages do not depend on tRPC,
React or the WebSocket transport.

## Checks and production

```bash
pnpm web:generate-api
pnpm web:check
pnpm web:build
pnpm --filter @gsm-agent-kit/web exec playwright install chromium
pnpm web:test
```

OpenAPI types in `src/api/schema.d.ts` remain generated from FastAPI. The exporter
does not load local secrets or start hardware. shadcn component configuration is
in `components.json`, with generated sources under `src/components/ui`.

Playwright starts the actual Python composition with temporary SQLite and fake
device/AI ports, the actual tRPC gateway and the production browser build. It
covers live SMS/reply/submission updates, reconnect catch-up, WebSocket auth,
SPA navigation, capability gating, manual/unknown outcomes without resend,
balance, errors and mobile layout. No modem, paid AI or real credentials are used.
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` can select an existing local Chrome.

Build assets are in `apps/web/dist`. Serve them with SPA fallback to `index.html`.
Forward `/api` and `/health` to Python, and `/trpc` with WebSocket upgrade headers
to the gateway. Preserve the public Host and Origin headers; they must match.
Do not cache API responses or retry submission POSTs. Use TLS outside trusted
local development; the browser automatically uses `wss:` under HTTPS.

The gateway runs using `pnpm --filter @gsm-agent-kit/web realtime` independently
of Vite. Gateway runtime dependencies include `tsx` in the current development
profile; static assets alone do not provide realtime. Container packaging remains
a separate deployment task.

Original code remains all rights reserved. Third-party notices, including shadcn,
Radix, Lucide, React, React Router and tRPC, are preserved in
`public/third-party-notices.txt` and copied into the static output.
