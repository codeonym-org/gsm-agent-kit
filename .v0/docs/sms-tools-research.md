# Linux SMS integration options

Researched 2026-10-13 against project documentation and interface specifications. Actual compatibility depends on inspecting the attached modem, its firmware and exposed ports, and testing the SIM/network SMS service; these sources do not establish that the attached device works.

## ModemManager: preferred when it already manages the device

ModemManager is the standard Linux WWAN daemon on many distributions. Its messaging D-Bus interface provides `List`, `Create`, `Delete`, and an `Added(path, received)` event. The interface requires a modem ready for cellular registration and, for 3GPP, an unlocked valid SIM. List existing messages at startup, then subscribe to events. [Project overview](https://modemmanager.org/), [official messaging specification](https://raw.githubusercontent.com/linux-mobile-broadband/ModemManager/main/introspection/org.freedesktop.ModemManager1.Modem.Messaging.xml).

`Added` can fire before all multipart SMS segments arrive. Check the SMS `State` and wait until `RECEIVED` (numeric value 3) before processing text. Ignore locally created messages and distinguish delivery reports from incoming text. [Messaging specification](https://raw.githubusercontent.com/linux-mobile-broadband/ModemManager/main/introspection/org.freedesktop.ModemManager1.Modem.Messaging.xml), [SMS state enum](https://github.com/linux-mobile-broadband/ModemManager/blob/main/include/ModemManager-enums.h).

To reply, call `Messaging.Create` with destination `number` and `text`, then call `Sms.Send` on the returned object. Text is UTF-8 and long outbound messages are split into parts. `Send` queues delivery; it is not a guarantee of receipt by the destination phone. Delivery reports have their own PDU type and delivery state. [Official SMS specification](https://raw.githubusercontent.com/linux-mobile-broadband/ModemManager/main/introspection/org.freedesktop.ModemManager1.Sms.xml).

The upstream Python example uses `libmm-glib` through GObject Introspection, requiring installed ModemManager, libmm-glib and its typelibs. This is a supported integration path; a Python D-Bus client can also address the published interfaces directly. [Upstream Python example README](https://chromium.googlesource.com/external/gitlab.freedesktop.org/mobile-broadband/ModemManager/%2B/bc7198df8a3217d29c936fccde66820774228e30/examples/sms-python/README).

Application design recommendation (inference): use one persistent Python service, store received messages and processing status in SQLite, and place any HTTP API/webhook adapter above that service. Subscribe before reconciling the startup list, persist before replying, deduplicate events, and reconnect/reconcile after daemon restarts. D-Bus is the native event/API boundary; HTTP forwarding is application code.

## Gammu SMSD: alternative for a compatible AT modem

Gammu SMSD periodically scans the modem, stores received SMS in a configured backend, and sends queued outbound messages. It supports files and database backends, and provides `gammu-smsd-inject` and status monitoring. [Official SMSD overview](https://wammu.eu/smsd/).

`RunOnReceive` executes a program after receiving messages, passing message identifiers and environment fields including sender, text and decoded multipart text. On POSIX, SMSD waits for the hook to finish, so a hook should quickly enqueue work rather than run a slow application or HTTP request inline. Multipart messages can supply multiple identifiers. [Official hook documentation](https://docs.gammu.org/smsd/run.html).

Reply by enqueueing with `gammu-smsd-inject`, writing to a supported outbox backend, or calling Python `gammu.smsd.SMSD.InjectSMS()`. The Python API also exposes daemon status. [Official SMSD usage](https://docs.gammu.org/smsd/usage.html).

Application design recommendation (inference): persist incoming messages using the files or SQL backend, use a short hook to notify a worker, and expose API/webhook delivery from that worker. Prefer this if direct AT SMS works but ModemManager does not expose usable messaging support. Give the selected modem manager exclusive responsibility for its control port.

## Decision and verification

1. Inspect USB identity, serial/network ports, existing daemon ownership, SIM readiness and registration.
2. If ModemManager exposes messaging, prefer its existing D-Bus API to avoid replacing the device manager.
3. If it does not, establish whether the device exposes a compatible AT port before evaluating Gammu; consult its device database as supporting evidence, then test locally. [Gammu documentation and compatibility guidance](https://wammu.eu/docs/).
4. Verify receive events with a fresh SMS and a multipart SMS. Verify replies separately to a chosen test number, including Unicode text and network failure handling.

No packages were installed and no SMS was sent as part of this research.
