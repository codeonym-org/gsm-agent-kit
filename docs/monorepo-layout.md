# Monorepo layout

The repository skeleton follows this layout. The original draft is archived
in `.v0/src/gsm_agent`; implementation will follow agreement on the layers.

LangChain separates core primitives, its main library, provider integrations,
and integration contract tests into independently packaged libraries under
[`libs/`](https://github.com/langchain-ai/langchain/tree/master/libs).
Each library owns its metadata and tests. Adopt those package boundaries while
keeping deployed applications and hardware deployment recipes explicit.

```text
gsm-agent-kit/
  libs/
    core/                       # gsm-agent-core
    gsm-agent/                  # gsm-agent: reusable application workflows
    integrations/
      modems/
        zte-http/               # gsm-agent-zte-http
        serial-at/              # gsm-agent-serial-at
        modemmanager/           # gsm-agent-modemmanager
      ai/
        langchain/              # gsm-agent-langchain
      storage/
        sqlite/                 # gsm-agent-sqlite
    standard-tests/             # gsm-agent-standard-tests
    kit/                        # gsm-agent-kit: curated install extras
  apps/
    server/                     # API, DI composition and runtime
    web/                        # browser UI
    cli/                        # device discovery/setup/diagnostics
  examples/
    sms-assistant/
    sms-gateway/
  deploy/
    images/                     # server/adapter Dockerfiles
    compose/                    # runnable deployment profiles
    host/                       # device permissions and host prerequisites
  docs/
  scripts/                      # repository development tooling
  tests/
    e2e/                        # assembled-system tests
  pyproject.toml                # workspace membership and shared tooling
  uv.lock                       # development workspace lock
```

These directories and Python package scaffolds exist, but adapter/application
behavior is not implemented. Package-name availability on PyPI is unverified.

## Package conventions

Every implemented Python library has its own `pyproject.toml`, `README.md`,
`src/<unique_import_package>/`, `tests/`, and typing marker where applicable.
For example, ZTE code lives under `src/gsm_agent_zte_http/`; it does not extend
another distribution's `gsm_agent` directory. Dependency declarations determine
what a consumer installs. Use a uv workspace for coordinated local development;
deployment installs the selected application and integrations rather than every
workspace member. Published libraries have their own version metadata.

`integrations` and its category folders group packages; they are not Python
distributions. A hardware model is configuration within an adapter when it
shares a protocol, and a separate integration when its behavior/dependencies
justify that boundary. Do not make a package or image for every model by default.

`standard-tests` supplies reusable adapter contract tests; it does not contain
the entire repository test suite. Integrations keep their own unit/protocol tests.

`kit` supplies explicit optional installation bundles; core contracts must not
depend on it. Its final relationship to the CLI/server will be decided during
runtime-layer design.

## Layer direction to discuss next

Core owns framework-independent domain types and public capability contracts.
The main library owns use cases/CQRS and application ports. Integrations implement
those contracts. Apps compose libraries and expose transports. Hexagonal layers
remain inside these boundaries rather than automatically becoming distributions.

API, DI and runtime wiring belong to the server application; Mediary remains in
the application library, and hardware/AI dependencies remain in integrations.
The exact ownership of individual ports and settings is deliberately deferred
to the layer discussion.

Deployment image/profile selection follows integration dependencies and transport
access requirements. Mounting installation media does not expose modem interfaces.
Frontend packaging uses its own JavaScript tooling if that stack is selected;
it is not a Python workspace member.
