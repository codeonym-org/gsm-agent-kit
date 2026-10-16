# gsm-agent-zte-mf833t

Model-specific ZTE MF833T adapter for its HTTP management interface. Implements
`device.status.read`, `sms.inbox.read` and `sms.send`. USSD follows separately.

Settings belong to this integration: `ZteMf833tSettings(base_url, timeout_seconds)`.
The URL defaults to `http://192.168.0.1`; timeout defaults to three seconds and
covers the entire observation, including model identification and status reads.
The adapter owns its HTTP client and closes it via `close()`.

The installed package depends only on core and HTTPX. It requires an IP route to
the management interface. No serial utility, ModemManager, USB control, installer
media, driver install or privileged container is needed for this HTTP adapter.
HTTP proxy environment variables are ignored and redirects are not followed.

## Observations and compatibility

The adapter identifies the frontend's `DEVICE` value, then reads only firmware,
hardware revision, provider, network type and signal bars from goform. It does
not request phone numbers, IMSI, IMEI, SMS contents or settings changes during status inspection.
An explicit inbox scan reads sender addresses and message contents for ingestion.

Adapter ID/version and declared model are separate from `observation` values.
Unknown identity, model mismatch, offline transport, login requirements and
malformed payloads produce explicit availability/issues. Support remains fixed.
Missing firmware/hardware is unknown; an unverified variant is untested.
Only a matching device-verification record establishes verified compatibility.
Protocol fixtures alone never do so. Verification applies only to implemented
status inspection and inbox reading. Sending has fixture evidence only; overall
compatibility remains `untested` until every declared capability is device-verified.
This does not imply USSD or support for every device from the same manufacturer.

`http-management` records the observed management access mode, not a claim about
USB composition, AT ports or registration on the cellular network. `ready` means
the status interface answered validly. Signal percent is the device's 0–5 bar
level multiplied by 20; it is not an RF power measurement.

## Verification

Hardware-free protocol and API tests cover known and unknown firmware, model
mismatch, unavailable hardware, authentication, bad responses, cancellation and
whole-operation deadlines. The fixture profile is firmware
`BD_WANAMARMF833TV1.0.0B04`, revision `djtA`, HTTP management access.

On 2026-10-16, the implemented adapter successfully ran `describe()` and the
typed status port against the attached MF833T. It observed the model marker,
firmware and hardware revision above, and valid provider, LTE and five-bar
status. Both operations closed their HTTP resources normally. Only GET requests
were made; no SMS, USSD, configuration changes or subscriber identifiers were
requested. The manifest records this device-verification evidence for status
inspection only. The assembled API is tested separately against a fake HTTP
device, keeping CI independent of hardware.

The inbox capability was also verified on 2026-10-16 against this exact variant.
The real `sms_data_total` command repeatedly returned its first page despite
different page numbers. The working command is `sms_page_data` with zero-based
pages. Ten-row reads traversed the complete stored scope, including outbound
rows; only received tags `0`/`1` became observations. The adapter returned all
36 received messages. No contents, sender numbers or subscriber identifiers are
included in fixtures or this repository. Only GET requests were issued, with no
send, mark-read, delete or configuration requests. The assembled server/API and
SQLite ledger were then verified against this device, using a temporary database:
existing messages stayed baselined and record identities survived restart.

## Inbox behavior and settings

`scan()` performs model/status checks and reads the device database
(`mem_store=1`, `tags=10`, descending IDs). It either returns the complete scanned
scope or raises a normalized `InboxReadError`. It never returns successful
truncation after a malformed, repeated or failed page or a pagination cap.
Inbox movement can prevent an atomic view; conflicting slot observations fail
the scan for retry. Wire bodies decode as strict UTF-16BE; partial concatenated
messages carry `complete=False` so the application can baseline them safely.

`ZteMf833tSettings` additionally accepts `inbox_timeout_seconds=10`,
`page_size=50`, `max_pages=100`, `storage_generation="initial"` and
`subscription_generation="initial"`. The inbox timeout includes waiting for the
scan lock, identification and every page; the status timeout remains separate.
External cancellation propagates and does not become an empty inbox.

The adapter does not read IMSI/ICCID or automatically detect SIM/storage
replacement. Set a new opaque subscription generation after a SIM change; set
a new storage generation after resetting or replacing storage. Device-retained
messages keep their occurrence identity across a subscription change, while the
ledger marks their attribution uncertain. Provider slot/sender/timestamp evidence
keeps partial completion stable; completed body changes distinguish slot reuse.
Two otherwise identical receipts with identical evidence remain indistinguishable.
While an occurrence is incomplete, matching slot/sender/timestamp evidence is
treated conservatively as its continuation even if the body changes; this can
suppress an ambiguous reuse of that same evidence rather than reply to backlog.
See the [server configuration](../../../../apps/server/README.md) for env names.

## SMS submission

The typed `sms.send` port exposes `SmsSendConstraints` and accepts one immutable
`PreparedSms`, including separate message and attempt IDs. GSM7 is limited to
160 units (extension characters count twice); BMP UCS2 is limited to 70 units.
It validates the prepared part and never truncates, transliterates, splits or retries it.

Each submission budget covers the operation lock, model/status checks, the
single `SEND_SMS` POST and asynchronous `sms_cmd_status_info` completion checks
with `sms_cmd=4`. HTTP acknowledgement alone is insufficient. Completion `3`
means submission acceptance; `2` means rejection. Timeouts or malformed/lost
responses after entering POST are unknown. Before POST, unavailable identity,
invalid input or an expired lock budget are not-submitted. Cancellation propagates.
An uncertain operation latches the adapter busy for subsequent writes; the
application ledger also quarantines uncertain attempts across restart.

Adapter settings: `send_timeout_seconds=30`, `send_poll_interval_seconds=1`.
The application owns normalization, natural splitting, output caps, durable intent
and progress. Sending has hardware-free fixtures and assembled API tests; no
new live SMS submission has been performed for this implementation.
