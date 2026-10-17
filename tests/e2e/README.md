The operator console's assembled-system runtime is `console_backend.py`.
Playwright tests live with the UI in `apps/web/tests/console.spec.ts` and launch
this runtime and the tRPC WebSocket gateway automatically with `pnpm web:test`, after `pnpm web:build`.

It composes the production API, dependency injection, Mediary handlers, workers
and SQLite stores with simulated device and AI ports. Fixture controls are
test-only loopback routes, never production endpoints. All databases are temporary;
hardware, SMS networks, external AI services and real credentials are unnecessary.
