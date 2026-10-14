# GSM Agent Kit

A modem-independent GSM toolkit monorepo under development.

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
  integrations/       Modem, AI and storage integrations
  standard-tests/     Shared integration contract tests
  kit/                Optional installation bundles
apps/                 Server, CLI and browser UI
deploy/               Images, Compose profiles and host setup
examples/             SMS assistant and gateway examples
tests/e2e/            Assembled-system tests
.v0/                  Archived reference implementation
```

The Python workspace has 11 scaffold packages. Each owns its dependencies,
README, source namespace, typing marker and test directory. Adapters and apps
are not operational yet; frontend tooling and deployment recipes are deferred
until their design is agreed.

## Develop

```bash
uv sync --all-packages --all-extras
uv run ruff check .
uv run ruff format --check .
```

`uv.lock` coordinates local development. `.v0` is excluded from workspace
membership, linting and test discovery. Select a package when working on it,
for example `uv run --package gsm-agent-core python`.

The `gsm-agent-kit` package declares installation extras: `server`, `cli`,
`zte-http`, `serial-at`, `modemmanager`, `langchain`, and `sqlite`. These currently
select scaffold packages; they do not yet provide modem drivers or services.
No packages or images have been published.

See [the proposed monorepo layout](docs/monorepo-layout.md) for the planned
libraries, integrations, applications, and deployment structure.

The original working draft is preserved in [`.v0/`](.v0/README.md) as a reference
for the new implementation. Its source, tests, scripts, dependency metadata,
device investigations, and local configuration/data were archived together.
The archived virtual environment may contain paths from its previous location;
recreate it before attempting to run the draft from `.v0`.

Keep `.v0` until the replacement covers the required behavior. It can then be
removed explicitly. Local secrets, databases, and environments remain ignored.
