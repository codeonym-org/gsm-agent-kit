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
The smoke target adds only isolated deployment fixtures on top of production.
`python scripts/smoke_containers.py` validates the production image and the
assembled smoke system. See [Compose usage](../compose/README.md).

The build follows uv's documented [non-editable workspace image pattern](https://docs.astral.sh/uv/guides/integration/docker/).
Runtime environment configuration uses Compose's
[`env_file` and service settings](https://docs.docker.com/reference/compose-file/services/).
