# gsm-agent-core

Framework-independent domain types and capability contracts.

Owns immutable device IDs, model and adapter manifests, descriptors, status
observations, inbox source/observation schemas and canonical typed capability lookup.
Implemented contracts are `device.status.read`, `sms.inbox.read`, `sms.send` and
`carrier.balance.read`. Each adapter binds only the capabilities it implements.

Support and availability are separate: lookup returns a supported port even
when its status is unavailable. Bindings are immutable, use canonical catalog
keys and are type-checked without casts in consumers.

Inbox snapshots include complete and incomplete observations. This preserves
partial-message identities during baselining without treating a partial as a
replyable message. Scans either cover the declared storage scope or raise
`InboxReadError`; no mark-read/delete operation is implied.

The sending port exposes typed single-segment encoding constraints and accepts
`PreparedSms` with message and attempt identities. `SmsSubmissionResult`
distinguishes not-submitted, rejected, accepted and unknown outcomes. The core
validates GSM7/UCS2 units without any provider encoding names or delivery claims.

This package depends only on the Python standard library. API, DI, CQRS, AI
and device libraries belong to consumers or integrations.

`AIAgent.invoke` returns a structured `ReplyDecision`; `stream` yields validated
complete decisions. `AgentInput` carries an opaque thread ID and plain
`ChatMessage` values. Ignore decisions require spam or automated-notification
reasons; replies require nonempty text. Framework messages, provider clients,
credentials and conversation persistence stay outside the port.

Python import: `gsm_agent_core`.

`BalanceReader.reserve()` returns an exclusive `BalanceSession` without sending
USSD. The session consults a reviewed carrier policy once and releases only its
own reservation. A foreign session is busy, never implicitly cancelled.
Adapters own protocol decoding, response freshness and uncertain-session gating.
`BalanceObservation` preserves raw text and a timezone-aware observation time;
optional `CreditBalance` and `SmsAllowance` are distinct, with conditions intact.
Missing parsed values are `None`, not zero. No generic USSD execution or menu
continuation capability is exposed. The ZTE adapter does not bind this contract.
