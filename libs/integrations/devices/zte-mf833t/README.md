# gsm-agent-zte-mf833t

Model-specific ZTE MF833T adapter for its HTTP management interface. Implements
only `device.status.read` in this slice. SMS and USSD contracts follow separately.

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
not request phone numbers, IMSI, IMEI, SMS contents or settings changes.

Adapter ID/version and declared model are separate from `observation` values.
Unknown identity, model mismatch, offline transport, login requirements and
malformed payloads produce explicit availability/issues. Support remains fixed.
Missing firmware/hardware is unknown; an unverified variant is untested.
Only a matching device-verification record establishes verified compatibility.
Protocol fixtures alone never do so. Verification applies only to implemented
status inspection, not to SMS, USSD or every device from the same manufacturer.

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
