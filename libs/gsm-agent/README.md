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
storage implementation or vendor API is imported by these workflows.

`SendSms` is a command over `SmsSender` and `SubmissionStore`; `GetSubmission`
is a read-only query. One application policy normalizes Markdown/HTML, preserves
text and links, prefers natural boundaries and caps transmitted characters and
part count using typed adapter encoding constraints. Limits include numbering.
Unsupported Unicode is rejected explicitly.

Intent and attempts commit before I/O. Replaying the same device-scoped request
UUID preserves its plan and accepted progress; conflicts return an explicit
error. Known-not-submitted parts can resume on an explicit replay. Unknown or
rejected parts stop; cancellation and interrupted attempts remain unknown.
No accepted part is automatically resubmitted. Acceptance is not delivery.
AI orchestration follows in a separate ticket.

Python import: `gsm_agent`.
