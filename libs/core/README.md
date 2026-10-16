# gsm-agent-core

Framework-independent domain types and capability contracts.

Owns immutable device IDs, model and adapter manifests, descriptors, status
observations, inbox source/observation schemas and canonical typed capability lookup.
Implemented capabilities are `device.status.read` and `sms.inbox.read`; sending, USSD and other capabilities will be added alongside
their behavioral contracts rather than advertised ahead of implementation.

Support and availability are separate: lookup returns a supported port even
when its status is unavailable. Bindings are immutable, use canonical catalog
keys and are type-checked without casts in consumers.

Inbox snapshots include complete and incomplete observations. This preserves
partial-message identities during baselining without treating a partial as a
replyable message. Scans either cover the declared storage scope or raise
`InboxReadError`; no mark-read/delete operation is implied.

This package depends only on the Python standard library. API, DI, CQRS, AI
and device libraries belong to consumers or integrations.

Python import: `gsm_agent_core`.
