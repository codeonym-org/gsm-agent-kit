# Adapter-specific images

`server.Dockerfile` provides the `zte-mf833t` production target and a separate
`smoke` target. Build from the repository root:

```bash
docker build -f deploy/images/server.Dockerfile --target zte-mf833t -t gsm-agent-kit/zte-mf833t:local .
```

The builder uses uv 0.8.22 and the committed `uv.lock` with `--locked`, `--no-dev`
and `--no-editable`. Only `gsm-agent-server[zte-mf833t,inbox,sms,ai]` and its
transitive dependencies are installed. Optional serial, ModemManager and
simulated device packages, development tools, uv itself and workspace source
are excluded from the runtime. No compiler or operating-system device services
are installed. The multi-stage runtime uses Python 3.13 slim Bookworm; uv's image
is version-pinned while the Python minor tag receives patch updates. No registry
publication or automatic image release is configured.

The allowlisted `.dockerignore` excludes root configuration, local environments,
device databases, `.v0`, Git metadata, browser dependencies and package tests.
Local `.owner.lock` sidecars are excluded as well. The server's pure-Python
filelock dependency uses native OS locking without a host daemon or extra
container permissions.
The smoke target adds only isolated deployment fixtures on top of production.
`python scripts/smoke_containers.py` validates the production image and the
assembled smoke system. See [Compose usage](../compose/README.md).

The build follows uv's documented [non-editable workspace image pattern](https://docs.astral.sh/uv/guides/integration/docker/).
Runtime environment configuration uses Compose's
[`env_file` and service settings](https://docs.docker.com/reference/compose-file/services/).

## Production console and gateway

`web.Dockerfile` uses Node 24 with the workspace's pinned pnpm 11.26.0 to build
the SPA and bundle the gateway with esbuild. Its separate runtime targets are:

- `console`: Caddy 2 Alpine, static SPA/assets/notices and the routing Caddyfile.
- `realtime`: Node 24 slim, the bundled gateway and third-party notices.

Neither target copies workspace source, node_modules or provider configuration.
The Caddy image also contains no Node runtime. The gateway uses its JavaScript
ws implementation without optional native accelerators. Build tools remain in
the builder stage. Docker base tags track updates within their selected majors; images are built locally
and are not automatically published.

The root allowlist also permits the pnpm manifests and web build sources while
excluding local environments, browser test artifacts and generated outputs.
See [pnpm's Docker guidance](https://pnpm.io/docker) and Caddy's
[reverse proxy documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
for the build and WebSocket proxy behavior used here.
