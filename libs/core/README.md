# gsm-agent-core

Framework-independent domain types and capability contracts.

Owns immutable device IDs, model and adapter manifests, descriptors, status
observations and canonical typed capability lookup. The initial capability is
`device.status.read`; SMS, USSD and other capabilities will be added alongside
their behavioral contracts rather than advertised ahead of implementation.

Support and availability are separate: lookup returns a supported port even
when its status is unavailable. Bindings are immutable, use canonical catalog
keys and are type-checked without casts in consumers.

This package depends only on the Python standard library. API, DI, CQRS, AI
and device libraries belong to consumers or integrations.

Python import: `gsm_agent_core`.
