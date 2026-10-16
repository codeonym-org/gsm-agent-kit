# GSM Agent Kit operator console

React, TypeScript and Vite browser application. Uses the existing server API;
business workflows, normalization, device protocols and persistence remain in
the Python packages. JavaScript dependencies use the root pnpm workspace and
`pnpm-lock.yaml`. The Python workspace continues to use uv.

## Run locally

Use Node 24+ and pnpm 11.26.0 (pinned in root `package.json`). From the repository
root, install dependencies and start the backend and frontend in separate terminals:

```bash
uv sync --locked --all-packages --all-extras
pnpm install --frozen-lockfile
uv run --package gsm-agent-server --extra simulated gsm-agent-server
```

```bash
pnpm web:dev
```

Open http://127.0.0.1:5173. By default, the simulated device offers status only;
the UI explicitly shows that SMS and balance are unsupported. Select a configured
SMS-capable adapter and enable the server's inbox/submission/assistant settings
to operate those features. See the [server setup](../server/README.md).
No provider key belongs in the frontend or any `VITE_` variable.

Vite forwards `/api` and `/health` to `http://127.0.0.1:8000`. To use a different
backend, set `GSM_API_PROXY_TARGET` in the Vite process environment. This is a
server-side development/preview proxy setting, not a browser-selected target.
Enter the server's API access token using **API connection** if required. It
stays in memory, is cleared on disconnect/reload, and is never put in local
storage, URLs, logs or build assets. Provider credentials are never requested.

## Behavior

- Choose a logical cellular device, inspect adapter identity/version, verification
  metadata, device access, carrier/network and signal observations. Support and
  observed availability are displayed separately; network status is not evidence
  of SMS submission readiness or delivery.
- Inbox and reply jobs page through 25 records. Read views refresh every five
  seconds; the configured-device list refreshes every ten seconds. Loading,
  empty, offline, unavailable and error states are explicit. Connection failures
  retain and label previous observations; failed authentication clears them.
- Automatic-reply enablement and dry-run/live mode are read from the server.
  This first console does not edit runtime configuration or reveal model keys.
- Manual submission generates one request UUID before its POST, then shows
  normalized transmitted parts and acceptance/unknown evidence. Manual sending
  is independent of the assistant's dry-run setting. There are no automatic POST
  retries or resend controls. **Check progress** only performs a GET.
- Keep the displayed request UUID before leaving/reloading the page. **Find
  submission progress** can reopen it after reconnecting; reply jobs link their
  own submission IDs. Drafts and manual request IDs are not stored in the browser.
  Backend audit records remain durable. A new draft is an explicit new intention,
  subject to the server's uncertain-submission quarantine.
- Balance is on demand and offered only for `carrier.balance.read`. Refreshing
  observations never executes USSD. Unsupported adapters, including the current
  MF833T, show an explicit unsupported state without making balance requests.
- SMS and carrier text render as plain text, including untrusted HTML/Markdown.

## Contracts and checks

```bash
pnpm web:generate-api
pnpm web:check
pnpm web:build
pnpm --filter @gsm-agent-kit/web exec playwright install chromium
pnpm web:test
```

API types in `src/api/schema.d.ts` are generated from FastAPI OpenAPI. The
exporter does not start devices or read local `.env` settings. Regenerate after
server transport changes; CI checks for drift. `ApiClient` owns HTTP error
normalization, cancellation, timeouts and bearer headers. UI modules consume
typed results without importing application/domain/device implementations.

Playwright launches a real FastAPI/Dishka/Mediary runtime with temporary SQLite
databases and simulated device/AI ports, then opens the production browser build.
It covers incoming SMS → plain-text prepared reply → pending/accepted submission,
manual acceptance, unknown outcomes without resend, device capability gating,
on-demand balance, authentication, errors and mobile layout. Fixture controls
exist only in `tests/e2e/console_backend.py`, bound to loopback; the production
server does not mount them. Tests make no hardware or paid AI calls.

An existing Chrome installation can be used locally by setting
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` when running tests. CI installs Playwright's
matching Chromium. Screenshots/traces remain ignored local artifacts.

## Production output

`pnpm web:build` creates `apps/web/dist/`. Serve these static files behind the
same origin as `/api` and `/health`, with those prefixes forwarded to the backend.
Preserve authorization headers, disable caching of API responses and allow the
server's configured operation deadlines. Never enable automatic retries of
submission POST requests in a reverse proxy. Serve `index.html` for application
paths, leaving `/api` requests to the backend. Use HTTPS outside a trusted local
setup. Vite dev/preview servers are local development tools; distribution of
the frontend is separate from the Python wheels.

Original code remains all rights reserved. Bundled React runtime notices are
included in `public/third-party-notices.txt` and copied into the build output.
