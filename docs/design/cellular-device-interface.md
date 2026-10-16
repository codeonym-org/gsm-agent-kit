# Cellular device interface and capabilities

Status: design proposal. Device inspection and a typed status capability are
implemented with simulated and model-specific ZTE MF833T adapters.
The MF833T adapter records variant-specific verification evidence. SMS, USSD and
durable workflows below remain proposed contracts for subsequent slices.
`.v0` supplies reference behavior, not the new public contracts.

Domain terms follow the root [glossary](../../GLOSSARY.md). The glossary defines
meaning; the interface choices and implementation policies below remain a
proposal.

## Goal

An application selects a logical cellular device, discovers its supported capabilities,
and uses small, typed interfaces. Changing the adapter must not require changing
the workflows that use it. Protocol details, device pagination, encoding, serialization
of hardware operations, and vendor error interpretation belong in adapters.

The interface includes operation semantics, deadlines, failure outcomes and
configuration requirements, not just method names.

The application term is cellular device. A modem is one hardware category;
embedded SIM-capable modules and other cellular devices fit the same interface.
SMS is the first workflow, not a requirement for every device. Voice calling,
multimedia messaging and future operations belong to the global capability
catalog as their contracts are defined. Device categories do not imply support.

## Ownership

| Module | Owns |
| --- | --- |
| `gsm-agent-core` | Framework-independent schemas, capability keys, cellular device interfaces and operation outcomes |
| `gsm-agent` | CQRS handlers, inbox ingestion, reply policy, SMS planning, durable processing and carrier balance policy |
| Device integrations | Model-specific adapters, device protocols, supported-capability declarations, constraints and settings |
| AI/storage integrations | Implementations of application-owned AI and persistence ports |
| Server/CLI | Transport mapping, dependency injection, configuration loading and adapter lifecycle |
| `standard-tests` | Reusable behavior checks through device capability interfaces |

Core imports no Mediary, FastAPI, Dishka, LangChain or hardware library. Device
integrations depend on core. The application owns workflow dependencies that
have no independent device-facing meaning, such as its processing ledger.

## Model-specific adapters and versions

Every newly supported device model gets its own identified, versioned adapter.
For example, the initial ZTE MF833T adapter is specific to that model rather
than a declaration that all ZTE HTTP devices behave identically. Each adapter
selects capabilities from the global catalog and supplies its own settings,
dependencies and verified device variants.

Keep three kinds of version evidence distinct:

| Identity/version | Meaning |
| --- | --- |
| Adapter ID and release/build version | Which integration implementation is installed |
| Device model and hardware revision | Which physical model/variant is attached |
| Device firmware version and operating mode | Which device behavior and exposed transports were tested |

Adapter metadata records those compatibility conditions, required transports,
dependencies, declared capability contracts and verification evidence. Runtime
descriptions report the actually opened device and selected adapter version.
An untested firmware or mode is identified as untested; model-name matching
alone is not evidence that every advertised operation works.

Adapters may share HTTP, AT or ModemManager protocol implementation internally.
Shared protocol code does not replace model-specific adapter identity, version
or capability verification. New firmware may require a new adapter release or
additional tested compatibility entries for the existing model.

Support grows continually through discovery, implementation, contract tests,
opt-in device verification and registration of a versioned adapter. Adding an
adapter does not require changing existing workflows. Adding a new kind of
operation requires a new core capability contract and the workflows that use it.

## Capability selection

Prefer typed capability lookup over a universal `execute(name, payload)` method
or a large cellular device interface that every adapter must partially implement.

Conceptual interface, with schema definitions omitted:

```python
class CellularDevice(Protocol):
    async def describe(self) -> DeviceDescriptor: ...

    def get[P](self, capability: CapabilityKey[P]) -> P | None: ...


class SmsSender(Protocol):
    async def submit(self, sms: PreparedSms) -> SmsSubmissionResult: ...


class SmsInbox(Protocol):
    async def scan(self) -> InboxSnapshot: ...


class DeviceStatusReader(Protocol):
    async def read(self) -> DeviceStatus: ...


class UssdClient(Protocol):
    async def exchange(self, code: UssdCode) -> UssdReply: ...
```

`CapabilityKey[P]` pairs a globally defined identifier with its port type. The
public catalog exports canonical keys; adapters select those keys rather than
inventing their own names. For example:

```python
sender = device.get(SMS_SEND)  # SmsSender | None
if sender is None:
    raise UnsupportedCapability("sms.send")
result = await sender.submit(prepared_sms)
```

The lookup is synchronous and performs no device I/O. A port is returned for a
supported capability even when the device is offline. `None` means unsupported,
not temporarily unavailable. The descriptor and lookup must agree for the
lifetime of an opened adapter. Reopening after a firmware/configuration change
may produce a different supported set.

The typed key mechanism needs a small implementation and type-checking proof
before committing to it. If it requires repeated casts in callers, reconsider
explicit typed accessors. Do not export an untyped dictionary as a substitute.

## Descriptor and catalog

`DeviceDescriptor` contains a configured logical cellular device ID, adapter
identifier and release/build version, optional manufacturer/model/firmware
observations, supported capabilities and
their constraints. Each observation carries a timestamp and distinguishes an
unknown value from an observed value.

Capabilities declare support; availability is an observation. A supported USSD
capability may currently be busy or unavailable. Failed probes must not silently
erase support. `describe()` uses bounded, non-mutating checks and can return
cached metadata with unknown/stale availability when the device cannot be read.
Invalid adapter configuration fails during opening instead.

Proposed initial catalog:

| Key | Interface | Essential contract |
| --- | --- | --- |
| `sms.send` | `SmsSender` | Submit one prepared single-segment SMS and report the submission outcome |
| `sms.inbox.read` | `SmsInbox` | Read complete inbound messages without marking them read or deleting them |
| `device.status.read` | `DeviceStatusReader` | Return normalized observations with explicit unknown values |
| `ussd.exchange` | `UssdClient` | Start one exchange, collect its response and release the session |

Relevant constraints include supported SMS encodings and segment limits, inbox
storage coverage, and USSD response support. Constraints are defined per
capability, not arbitrary vendor JSON. Operation timeout and polling interval
are adapter settings, not hardware capabilities.

Future catalog candidates include voice calling, multimedia messaging, SMS
deletion, mark-read, delivery reports, native incoming notifications and
interactive USSD sessions. Add their contracts
when implementing behavior that needs them. An adapter must not claim support
because an untested firmware menu mentions a feature.

Describe support per opened device/configuration, not just per model name. For
the archived ZTE profile, distinguish demonstrated SMS behavior from the USSD
timeout investigation. An implemented USSD interface does not promise that a
particular carrier consultation will succeed. A voice-only device can implement
the cellular device interface without offering SMS or USSD. Workflows check for
their required capabilities rather than inferring them from a device category.

## SMS schemas and submission semantics

Core defines its own immutable schemas. Provider objects and vendor enums do
not escape adapters. Proposed minimum schemas:

| Schema | Meaning |
| --- | --- |
| `CellularDeviceId` | Configured stable logical cellular device identity; not a transient USB path |
| `SmsAddress` | Address value with explicit kind: international number, national number, short code or alphanumeric sender |
| `IncomingSms` | Inbox source, stored-message identity, sender, complete body, optional carrier timestamp and observation timestamp |
| `PreparedSms` | Outgoing message identity, submission attempt identity, destination, single-segment text and selected supported encoding |
| `SmsSubmissionResult` | Outgoing message and attempt identities, outcome, optional provider reference and normalized reason |
| `InboxSnapshot` | Complete scan result, source scope and scan start/end timestamps |

An inbound alphanumeric sender is not automatically a valid reply destination.
National numbers require configured numbering context before normalization;
dropping punctuation alone cannot establish international identity.

Submission outcomes are:

| Outcome | Meaning | Automatic retry |
| --- | --- | --- |
| `not_submitted` | Adapter knows the request did not reach a point where it could take effect | Only when the reason is retryable |
| `rejected` | Device/provider explicitly rejected submission | Only after resolving the reason or under an explicit policy |
| `accepted` | Device/provider acknowledged submission according to its protocol | No |
| `unknown` | Submission may have taken effect; evidence is insufficient | No blind retry |

`accepted` does not mean delivered to the recipient. Delivery requires separate
evidence. The ZTE implementation must inspect asynchronous completion status;
an initial HTTP success alone is insufficient.

An outgoing message identity correlates its submission attempts; each attempt
has a distinct identity. Neither identity creates device idempotency. Persist
intent before calling the adapter. A crash or cancellation
after entering submission must leave the attempt uncertain until reconciled;
the adapter cannot guarantee returning a result if its process is killed.

Adapters do not silently truncate, transliterate or retry a possibly submitted
SMS. They validate prepared text against advertised constraints and perform
wire encoding. The application handles plain-text normalization, natural text
splitting, output limits and durable progress across multiple submissions.
Initial long replies comprise independent reply parts, each one single-segment
SMS message, matching `.v0`. Concatenated SMS with UDH is a separate future
contract because it changes capacity and recipient behavior.

## Inbox identity and ingestion

`scan()` hides device pagination and returns a complete scan of the advertised
storage scope, or raises a normalized read error. A failed page must not become
a successful empty or truncated inbox. Reads do not mark messages read, delete
messages or publish application events.

The scan is not an atomic snapshot unless the underlying device guarantees it.
Start/end timestamps expose that limitation; repeated scans tolerate overlap.
Incomplete multipart messages are held within the adapter until complete and
must not appear as replyable `IncomingSms` values. The snapshot can report a
pending count without exposing partial messages as complete ones.

Provider IDs may be reused. An inbox source distinguishes the logical cellular device,
relevant storage/SIM generation and storage location. Stored-message identity
combines that source with provider identity and suitable message evidence to
detect reuse. A configured generation is needed when an adapter cannot detect
a relevant source replacement. Changing the SIM must not automatically turn
messages retained in device storage into new messages; preserve their known
identities and distinguish uncertain subscription attribution. A content
fingerprint alone cannot distinguish two otherwise identical legitimate
messages; document that
limitation for adapters without reliable identity evidence.

The application persists observations and deduplicates before publishing
`SmsReceived`. Its ledger is independent of device unread flags. On first start,
the default baseline records existing messages without replying to the backlog.
Event delivery is at least once; handlers use durable processing identity.

Start with polling. Native adapter notifications can later wake an ingestion
scan, while the persisted ledger remains the authority for processing. There
is no need to require an event stream from every cellular device to implement listening.

## Balance consultation and CQRS

Balance is carrier policy, not a universal cellular device primitive. The application
maps a configured carrier consultation to `UssdClient.exchange()` and returns
raw carrier text, observation time and an explicit parsing status. Structured
credit balance or SMS allowance values are optional and require a recognized
response. Preserve currency and reported validity/scope conditions; a monetary
balance and an SMS allowance are separate observations. Do not invent a numeric
zero when parsing fails.

`GetBalance` is a query: it observes account information using the configured
consultation code. Starting and cleaning up a transient USSD session does not
turn that business operation into a command. Query inputs cannot accept an
arbitrary USSD code or follow purchase menus.

`SendSms` and `IngestInbox` are commands: they submit messages or change the
durable processing ledger. `GetDeviceDescriptor`, `GetDeviceStatus` and
`ListStoredMessages` are queries. `SmsReceived` is an event. Arbitrary USSD
execution or buying an SMS offer belongs to separately authorized commands.

The initial USSD interface owns only the session it starts. If another session
is active, return busy rather than cancelling someone else's operation.
Responses requiring a menu selection are returned as such, with no automatic
selection, and the owned session is released. Interactive session continuation
requires a separate future interface.

The HTTP transport must distinguish unsupported consultation, unavailable
device/carrier, busy session and deadline expiry. Increasing a timeout is not
evidence that a stuck carrier session has been fixed.

## Deadlines, concurrency and errors

Adapter settings define bounded operation budgets. A budget includes waiting
for an adapter's operation lock, device I/O and response polling. The adapter
serializes operations that share firmware state, including send and USSD when
needed. Callers must not learn vendor-specific lock ordering.

Each opened cellular device has one runtime owner. An in-process lock does not coordinate
two application processes; deployment must prevent competing owners or supply
an explicit ownership mechanism. Adapter opening/closing and resource cleanup
are wired by the runtime, outside individual CQRS handlers.

Read errors distinguish unsupported capability, unavailable device, busy,
deadline expiry and invalid protocol response. Diagnostic details are useful
but must not leak credentials or message bodies. SMS submission retains its
outcome semantics above even when a transport exception caused the failure.

## Domain scenarios and archive differences

| Scenario | Model consequence |
| --- | --- |
| The same cellular device reconnects at another USB path or HTTP address | Its logical cellular device identity is unchanged |
| A device supports voice calling but not SMS | Calling workflows can use it; SMS workflows report unsupported capability |
| Two models speak AT commands but differ in supported operations | Each has its own adapter and capability declaration; protocol implementation may be shared |
| A known model appears with untested firmware | Report the compatibility gap rather than treating model identity as verification |
| Inbox slot `7` is reused for a different message | The two occurrences have distinct stored-message identities |
| A SIM is replaced while old messages remain in device storage | Subscription identity changes; retained message identities do not automatically change |
| A supported SMS sender becomes unreachable | Capability availability changes; support remains declared |
| The carrier accepts a reply, but no delivery report arrives | Submission is accepted; delivery remains unconfirmed |
| A reply contains three numbered independent messages | It has three reply parts; it is not one concatenated SMS |
| A response reports 10 DH credit and 200 remaining SMS | Record credit balance and SMS allowance separately |
| A timeout follows submission and a retry is requested | The original attempt remains unknown; a retry could duplicate the message |

The archive contains terminology that must not be carried forward unchanged:

- `.v0` constructs `SmsMessage.modem_id` from the firmware row's `id`. That
  value is a provider storage identifier, not a logical cellular device identity.
- `.v0` uses `MessageState.SENT` after modem send completion. The new model
  calls that submission acceptance unless separate delivery evidence exists.
- `.v0` calls `delivered_text()` while recording accepted reply text. The new
  implementation must not imply confirmed delivery through that name.
- `.v0` stores numbered independent messages in `reply_parts`. Preserve the
  distinction between reply parts and concatenated SMS segments.
- `.v0` cancels a previously pending USSD session during balance consultation.
  The proposed interface returns busy for an existing session it cannot prove
  it owns; explicit recovery is a separate operation.

Conversation identity remains a later application-layer decision. The archive
groups history by sender phone number alone. With multiple SIMs or assistants,
that can combine exchanges from different local identities. The model must
decide which exchanges share a conversation before adopting a universal thread
key; this proposal does not silently change the user's existing memory policy.

## Contract verification

Reusable tests exercise the same capability interfaces as callers. An adapter
runs tests for every capability it advertises; a fake can exercise application
workflows but cannot prove the hardware adapter's conformance.

Initial behavior checks cover:

- Descriptor/lookup agreement and unsupported versus unavailable behavior.
- Complete inbox pagination, overlapping scans, ID reuse and multipart gating.
- No mark-read/delete effects during scans.
- Submission acceptance, explicit rejection and uncertain timeout; no hidden retry.
- Deadline expiry while queued versus after submission may have taken effect.
- USSD busy handling, owned-session cleanup and preservation of foreign sessions.
- Unknown status fields and preservation of carrier text when balance parsing fails.
- Restart recovery and replay without automatically resending uncertain attempts.

Protocol fixtures belong to each integration's own tests. Opt-in device checks
validate real firmware behavior; sending, deleting or executing USSD must never
be a default CI action.

## First implementation slice

Implement core schemas and the typed capability lookup with the ZTE MF833T adapter and
a deterministic fake. Prove the lookup types and submission outcomes first.
Then implement durable inbox ingestion and SMS submission workflows. Add the
configured balance query after its USSD contract tests, keeping unsupported and
timed-out outcomes visible.

Other model-specific adapters using serial AT or ModemManager will test whether
these seams hide real variation. Revise the contracts when a second implementation
exposes a mismatch; do not add methods merely to mirror vendor operations.
