# gsm-agent-sqlite

Implements the application-owned `InboxStore` port using aiosqlite. Owns durable
inbox observations, per-source/subscription baselines and a transactional event
outbox. It performs no device I/O and publishes no events itself.

`SqliteInboxStore.open(path)` creates the ledger; `close()` releases its worker
and connection. Keep the database across restarts. It is local device data and
must not be committed or attached to public issues.

The source key combines logical device ID, storage location and storage
generation. Subscription generation controls baselining and attribution without
changing identities of messages retained in device storage. Slot reuse with
different timestamp/sender/content creates a distinct occurrence. Completing a
partial preserves its record ID and baseline state. Identical receipts with
identical provider evidence cannot be distinguished by this protocol.
An incomplete occurrence with matching slot/sender/timestamp evidence is treated
as a continuation, preserving a baseline exclusion even under ambiguous slot reuse.

WAL, a process-local lock and SQLite transactions make baseline/observation/outbox
writes atomic. Older overlapping snapshots cannot regress committed observations.
Cancellation rolls back an uncommitted transaction. This does not provide a
distributed device ownership or event-dispatch lease; run one runtime owner.

Tests exercise real temporary SQLite databases, restart, two sources, overlapping
connections, multipart completion, slot reuse, SIM/storage replacement, rollback
and cancellation.

`SqliteSubmissionStore` implements the independent `SubmissionStore` port.
Requests are scoped by logical device and client UUID, with a digest to reject
conflicting input. Plans and message IDs are immutable; every adapter attempt has
a distinct persisted ID. An attempt commits before I/O, and completion updates
the attempt and part atomically. Startup converts unfinished attempts to unknown;
accepted parts stay accepted and pending parts stay pending. Unknown attempts
block new requests for the same device until separately reconciled. There is no
automatic resend, force retry or delivery inference. Keep this ledger across
restarts; the server defaults to a separate submissions database.
AI memory remains future work.

Python import: `gsm_agent_sqlite`.
