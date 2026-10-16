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

`SmsReceived` queues a durable, record-deduplicated reply when auto-reply is
enabled. `ProcessNextReply` is a command that generates a structured decision
through the core `AIAgent` port and delegates live sending to `SendSms`.
Model generation runs outside the ingestion deadline. A prepared decision
survives restart; interrupted generation is failed, and interrupted submission
is reconciled by reading its ledger, without sending again. There is no
automatic provider retry or SMS retry.

Conversation keys combine inbox source, subscription generation and normalized
international correspondent. National addresses require an explicit country
region; named senders and short codes are skipped. History contains bounded
user input and only the exact accepted reply parts; dry-run and ignored outputs
never become assistant history. The existing preparation policy owns output
normalization, splitting and limits for both live sending and dry-run previews.
`GetAssistantStatus` and `ListReplyJobs` are queries over local workflow state.

Python import: `gsm_agent`.

`ConsultBalance` is a Mediary query over `carrier.balance.read`. It checks support
before acquiring a session, uses a configured reviewed carrier consultation
policy, and shares one deadline across ownership acquisition and response I/O.
It never follows a menu or retries. An acquired session is released on success,
failure, timeout and cancellation, with an additional bounded cleanup budget.
Foreign-session errors do not call cleanup because no handle was acquired.
Cleanup failure prevents a successful result; an existing failure keeps its
original classification. Carrier parsers, if implemented by an adapter, must
preserve raw text and distinguish unknown credit/allowance from observed zero.
