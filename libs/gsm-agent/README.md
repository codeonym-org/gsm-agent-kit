# gsm-agent

Reusable application workflows and CQRS handlers.

The initial use cases are `ListAdapters`, `ListDevices`, `GetDevice` and
`GetDeviceStatus`. All are Mediary queries dispatched through `QuerySender`;
none are commands. Reads use an application-owned device-directory port and
the core cellular-device capability ports.

Description and status queries have a bounded budget, with separate unknown
device, unsupported capability and deadline errors. Concrete directories,
device lifecycle and transport error mapping live in the server or adapters.
`ListStoredMessages` is a query over an application-owned `InboxStore` port.
`IngestInbox` is a command: it scans the typed `sms.inbox.read` port, commits
observations and baselines, then dispatches durable `SmsReceived(record_id)`
events. The workflow lock and timeout include scanning, ledger updates and event
dispatch. Publication is at least once; consumers must deduplicate by record ID.

The persistence adapter owns atomic observation/baseline/outbox writes; no
storage implementation or vendor API is imported by these workflows. Outgoing
SMS and AI orchestration follow in separate tickets.

Python import: `gsm_agent`.
