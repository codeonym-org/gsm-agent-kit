# gsm-agent-kit

Optional installation bundles for GSM Agent Kit.

The `zte-mf833t` extra selects the server and ZTE MF833T HTTP integration.
It installs only that profile's declared runtime dependencies. Configure
`GSM_DEVICE__ADAPTER=zte-mf833t` to select it at runtime. See the
[server README](../../apps/server/README.md) for the workspace command and settings.

Add the `inbox` extra to select the server's SQLite-backed inbox support, then
set `GSM_INBOX__ENABLED=true`. The standalone combination is
`gsm-agent-kit[zte-mf833t,inbox]`; it adds no unrelated device or AI integrations.
The `sqlite` extra selects the persistence library without the server.

Other hardware/AI extras still select scaffolds. Packages are not yet
published; the extras can be exercised using workspace or built distributions.

Python import: `gsm_agent_kit`.
