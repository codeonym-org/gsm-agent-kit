import asyncio
import time
from datetime import datetime, timezone

import httpx

from gsm_agent.domain.balance import BalanceCode, BalanceResult
from gsm_agent.domain.errors import (
    BalanceTimeoutError,
    BalanceUnavailableError,
    ModemConnectionError,
    SmsSendFailedError,
    SmsSendUncertainError,
)
from gsm_agent.domain.sms import ModemStatus, PhoneNumber, SmsMessage
from gsm_agent.domain.sms_text import single_sms_capacity, sms_encoding, sms_units


class ZteModem:
    """MF833T goform API in USB network mode; one send at a time."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        page_size: int = 50,
        max_pages: int = 20,
        send_timeout: float = 30,
        ussd_timeout: float = 30,
    ):
        self.client = client
        self.page_size = page_size
        self.max_pages = max_pages
        self.send_timeout = send_timeout
        self.ussd_timeout = ussd_timeout
        # Serialize modem writes: balance consultations cannot overlap each other
        # or SMS sends. Reads can continue while waiting for the carrier.
        self._operation_lock = asyncio.Lock()

    async def _get(self, cmd: str, **params: object) -> dict:
        try:
            response = await self.client.get(
                "/goform/goform_get_cmd_process", params={"isTest": "false", "cmd": cmd, **params}
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("result") in ("failure", "fail"):
                raise ValueError("Invalid modem response")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise ModemConnectionError("Could not read modem API") from exc

    async def get_status(self) -> ModemStatus:
        data = await self._get("network_provider,network_type,signalbar,sms_unread_num", multi_data=1)
        try:
            return ModemStatus(
                str(data["network_provider"]),
                str(data["network_type"]),
                int(data["signalbar"]),
                int(data.get("sms_dev_unread_num", data["sms_unread_num"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ModemConnectionError("Invalid modem status response") from exc

    async def list_messages(self) -> list[SmsMessage]:
        messages: dict[str, SmsMessage] = {}
        previous_page: tuple[str, ...] | None = None
        for page in range(self.max_pages):
            data = await self._get(
                "sms_data_total",
                page=page,
                data_per_page=self.page_size,
                mem_store=1,
                tags=10,
                order_by="order by id desc",
            )
            rows = data.get("messages")
            if not isinstance(rows, list):
                raise ModemConnectionError("Inbox response missing messages (login may be required)")
            page_ids = tuple(str(row.get("id")) for row in rows if isinstance(row, dict))
            if rows and page_ids == previous_page:
                raise ModemConnectionError("Modem repeated an inbox page; refusing truncated snapshot")
            previous_page = page_ids
            try:
                for row in rows:
                    if str(row["tag"]) not in ("0", "1"):
                        continue
                    encoded = str(row["content"])
                    content = bytes.fromhex(encoded).decode("utf-16-be")
                    message = SmsMessage(
                        str(row["id"]),
                        str(row["number"]),
                        content,
                        str(row["date"]),
                        str(row.get("received_all_concat_sms", "1")) != "0",
                    )
                    messages[message.key] = message
            except (KeyError, TypeError, ValueError, UnicodeError) as exc:
                raise ModemConnectionError("Invalid inbox message encoding or fields") from exc
            if len(rows) < self.page_size:
                return list(messages.values())
        raise ModemConnectionError("Inbox exceeds configured pagination limit")

    async def send_sms(self, recipient: PhoneNumber, message: str) -> None:
        # Firmware's non-BMP encoder differs from UTF-16. Reject such input rather
        # than emitting corrupt SMS; BMP covers Arabic and common European scripts.
        if not message.strip() or any(ord(c) > 0xFFFF or 0xD800 <= ord(c) <= 0xDFFF for c in message):
            raise SmsSendFailedError("Unsupported SMS text")
        encoding = sms_encoding(message)
        if sms_units(message, encoding) > single_sms_capacity(encoding):
            raise SmsSendFailedError("Adapter only accepts one segment; split through the application")
        async with self._operation_lock:
            now = datetime.now().astimezone()
            offset = now.utcoffset()
            hours = (offset.total_seconds() if offset else 0) / 3600
            form = {
                "isTest": "false",
                "goformId": "SEND_SMS",
                "notCallback": "true",
                "Number": recipient.value,
                "sms_time": now.strftime("%y;%m;%d;%H;%M;%S;") + f"{hours:+g}",
                "MessageBody": message.encode("utf-16-be").hex().upper(),
                "ID": "-1",
                "encode_type": encoding,
            }
            try:
                response = await self.client.post("/goform/goform_set_cmd_process", data=form)
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise SmsSendUncertainError("Send request outcome is unknown") from exc
            if not isinstance(data, dict) or "result" not in data:
                raise SmsSendUncertainError("Modem returned no send acknowledgement")
            if data["result"] != "success":
                raise SmsSendFailedError("Modem rejected the SMS")
            deadline = time.monotonic() + self.send_timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(1)
                try:
                    status = await self._get("sms_cmd_status_info", sms_cmd=4)
                except ModemConnectionError as exc:
                    raise SmsSendUncertainError("Could not confirm SMS completion") from exc
                result = str(status.get("sms_cmd_status_result", ""))
                if result == "3":
                    return
                if result == "2":
                    raise SmsSendFailedError("Modem reported SMS send failure")
            raise SmsSendUncertainError("SMS completion timed out")

    async def consult_balance(self, code: BalanceCode) -> BalanceResult:
        async with self._operation_lock:
            started = False
            try:
                # Includes HTTP calls and polling in one overall deadline.
                async with asyncio.timeout(self.ussd_timeout):
                    status = await self._get("ussd_write_flag")
                    if str(status.get("ussd_write_flag")) == "15":
                        # The firmware UI initializes USSD by cancelling an old
                        # session and waiting for flag 13, not just an HTTP ACK.
                        try:
                            async with asyncio.timeout(3):
                                response = await self.client.post(
                                    "/goform/goform_set_cmd_process",
                                    data={"goformId": "USSD_PROCESS", "USSD_operator": "ussd_cancel"},
                                )
                                response.raise_for_status()
                                if response.json().get("result") != "success":
                                    raise BalanceUnavailableError("Modem rejected USSD session recovery")
                                while True:
                                    status = await self._get("ussd_write_flag")
                                    flag = str(status.get("ussd_write_flag", "unknown"))
                                    if flag == "13":
                                        break
                                    if flag != "15":
                                        raise BalanceUnavailableError(
                                            f"USSD session recovery failed (modem status {flag})"
                                        )
                                    await asyncio.sleep(0.25)
                        except TimeoutError as exc:
                            raise BalanceUnavailableError(
                                "Modem USSD is stuck pending (status 15); cancellation did not complete. "
                                "Check USSD in the modem web UI or restart the modem before retrying."
                            ) from exc
                    started = True
                    response = await self.client.post(
                        "/goform/goform_set_cmd_process",
                        data={
                            "isTest": "false",
                            "goformId": "USSD_PROCESS",
                            "USSD_operator": "ussd_send",
                            "USSD_send_number": code.value,
                            "notCallback": "true",
                        },
                    )
                    response.raise_for_status()
                    ack = response.json()
                    if not isinstance(ack, dict) or ack.get("result") != "success":
                        raise BalanceUnavailableError("Modem rejected the USSD balance request")
                    while True:
                        status = await self._get("ussd_write_flag")
                        flag = str(status.get("ussd_write_flag", "unknown"))
                        if flag == "15":
                            await asyncio.sleep(1)
                            continue
                        if flag == "16":
                            data = await self._get("ussd_data_info")
                            # This firmware's own UI decodes ussd_data as Unicode
                            # hex, including when the carrier used GSM on the air.
                            text = bytes.fromhex(str(data["ussd_data"])).decode("utf-16-be").strip()
                            if not text:
                                raise BalanceUnavailableError("Carrier returned an empty balance response")
                            return BalanceResult(
                                code.value,
                                text,
                                datetime.now(timezone.utc).isoformat(),
                                str(data.get("ussd_action", "0")) == "1",
                            )
                        if flag in ("3", "4", "unknown"):
                            raise BalanceTimeoutError("Carrier balance consultation timed out")
                        messages = {
                            "1": "USSD service is unavailable",
                            "2": "Carrier terminated the USSD session",
                            "10": "Carrier requested another attempt; no automatic retry was made",
                            "99": "USSD is unsupported by this modem/network",
                            "41": "Carrier does not support this USSD operation",
                        }
                        raise BalanceUnavailableError(messages.get(flag, "USSD balance request failed"))
            except TimeoutError as exc:
                raise BalanceTimeoutError(
                    "Modem accepted the balance request but no USSD response arrived before the deadline. "
                    "Check USSD in the modem web UI; increasing the timeout may not resolve a stuck session."
                ) from exc
            except (httpx.HTTPError, ModemConnectionError, ValueError, KeyError, TypeError) as exc:
                raise BalanceUnavailableError("Could not obtain a valid USSD balance response") from exc
            finally:
                if started:
                    # A response can leave a menu session open. Release it without
                    # ever selecting options that could subscribe/recharge/etc.
                    try:
                        async with asyncio.timeout(3):
                            await self.client.post(
                                "/goform/goform_set_cmd_process",
                                data={
                                    "isTest": "false",
                                    "goformId": "USSD_PROCESS",
                                    "USSD_operator": "ussd_cancel",
                                },
                            )
                    except (TimeoutError, httpx.HTTPError):
                        pass
