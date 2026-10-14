# Attached modem investigation

Inspected 2026-10-13 using read-only USB metadata, host routes, ModemManager,
and the device's own HTTP interface. No SMS sent, deleted, or marked read;
no modem settings changed and no packages installed.

## Verified device

- USB manufacturer/model: ZTE, Incorporated / inwi 4G MF833T.
- USB ID: `19d2:1405` (from `/sys/bus/usb/devices`).
- Firmware: `BD_WANAMARMF833TV1.0.0B04`; hardware: `djtA`.
- USB network interface: `enp3s0f3u3`; management URL: http://192.168.0.1/.
- Carrier: inwi; network: LTE; signal bars: 5.
- SMS capacity: 100 device slots, 26 used (25 received, 1 sent),
  plus 20 SIM slots, none used. 14 unread device messages at inspection.
- `mmcli -L` reports no modems; no USB serial tty interfaces were found.
  ModemManager/Gammu are therefore not immediately usable in the current mode.

## Firmware API evidence

Primary sources are the actual device frontend:
[service.js](http://192.168.0.1/js/service.js) and
[config.js](http://192.168.0.1/js/config/config.js).
These addresses are reachable on this machine's modem network.

- Configuration declares SMS and concatenated SMS support.
- GET `/goform/goform_get_cmd_process` with `cmd=sms_capacity_info`
  returns device/SIM capacity and usage; verified live.
- GET the same endpoint with `cmd=sms_data_total`, `isTest=false`,
  `page=0`, `data_per_page=1`, `mem_store=1`, `tags=10`,
  `order_by=order by id desc` returned one stored message; verified live.
  Its fields include `id`, `number`, `content`, `tag`, `date`, and multipart
  completion fields. Personal message data was not printed or committed.
- The frontend identifies unread messages by `tag == "1"`.
- POST `/goform/goform_set_cmd_process` with `goformId=SEND_SMS` uses
  `isTest`, `notCallback`, `Number`, `sms_time`, `MessageBody`, `ID`,
  and `encode_type`. The firmware frontend supplies encoding functions;
  copy their behavior when implementing the adapter.
- Sending is asynchronous: the frontend checks `cmd=sms_cmd_status_info`,
  `sms_cmd=4` after initial success. Initial success alone is insufficient.
- Frontend also defines delete, mark-read, and delivery-report operations.
  These were inspected in code, not exercised.
- Requests were made with `Referer: http://192.168.0.1/index.html`.
  Read requests worked without an explicit login in the current device session;
  authentication behavior after a restart is unverified.

No native webhook, WebSocket, or server-sent event interface was identified
in the inspected frontend. This is a finding about inspected code, not proof
that no such interface exists elsewhere.

## Recommended application

Use the existing Python `httpx` dependency to implement the existing
`application/ports/modem_port.py` interface against this device HTTP API.
No additional modem package is needed for this approach.

1. Poll the inbox every 2–5 seconds, with pagination, timeouts and backoff.
2. Wait for complete concatenated messages before processing.
3. Persist incoming messages and processing state in SQLite (Python standard
   library). Track message identity beyond ID alone because storage IDs may
   be reused. Do not use unread status as the processing ledger.
4. Baseline existing messages on first start to avoid replying to the backlog.
5. Publish an internal event or durable outgoing webhook for each new SMS.
6. Queue replies and check modem send completion. Ambiguous timeouts need
   reconciliation; blindly retrying can send duplicate replies.
7. Expose FastAPI endpoints for status and controlled sending if needed;
   the repository already declares FastAPI through its mediary extras.
8. Define retention and cleanup after durable storage, because modem storage
   is limited. Do not delete messages before durable processing.

Receive/send delivery, encoding (including Arabic and multipart SMS), restart
recovery, pagination boundaries, and authentication still need live validation.
There is no running listener or auto-reply service yet.

Alternative tool research and official citations:
[SMS tools research](sms-tools-research.md). Those alternatives require an
appropriate modem interface; changing USB mode is unnecessary for this HTTP
approach and was not attempted.
