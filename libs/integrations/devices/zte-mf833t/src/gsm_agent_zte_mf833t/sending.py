import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx
from gsm_agent_core.domain.devices import Availability, DeviceObservation, DeviceReadIssue, DeviceStatus
from gsm_agent_core.domain.submission import (
    PreparedSms,
    SmsEncoding,
    SmsSendConstraints,
    SmsSubmissionResult,
    SubmissionOutcome,
    SubmissionReason,
)

from gsm_agent_zte_mf833t.settings import ZteMf833tSettings


class ZteSmsSender:
    constraints = SmsSendConstraints()

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: ZteMf833tSettings,
        inspect: Callable[[], Awaitable[tuple[DeviceObservation, DeviceStatus]]],
        operation_lock: asyncio.Lock,
    ) -> None:
        self._client, self._settings, self._inspect = client, settings, inspect
        self._lock = operation_lock
        self._uncertain = False

    async def submit(self, sms: PreparedSms) -> SmsSubmissionResult:
        def result(outcome: SubmissionOutcome, reason: SubmissionReason | None = None) -> SmsSubmissionResult:
            if outcome is SubmissionOutcome.UNKNOWN:
                self._uncertain = True
            return SmsSubmissionResult(sms.message_id, sms.attempt_id, outcome, reason)

        try:
            self.constraints.validate(sms.text, sms.encoding)
        except ValueError:
            return result(SubmissionOutcome.NOT_SUBMITTED, SubmissionReason.INVALID_INPUT)
        entered_post = False
        try:
            async with asyncio.timeout(self._settings.send_timeout_seconds):
                async with self._lock:
                    if self._uncertain:
                        return result(SubmissionOutcome.NOT_SUBMITTED, SubmissionReason.BUSY)
                    if self._client.is_closed:
                        return result(SubmissionOutcome.NOT_SUBMITTED, SubmissionReason.UNAVAILABLE)
                    observation, _ = await self._inspect()
                    if observation.availability is not Availability.READY:
                        reason = {
                            None: SubmissionReason.UNAVAILABLE,
                            DeviceReadIssue.MODEL_MISMATCH: SubmissionReason.MODEL_MISMATCH,
                            DeviceReadIssue.AUTH_REQUIRED: SubmissionReason.AUTH_REQUIRED,
                            DeviceReadIssue.TIMEOUT: SubmissionReason.TIMEOUT,
                        }.get(observation.issue, SubmissionReason.UNAVAILABLE)
                        return result(SubmissionOutcome.NOT_SUBMITTED, reason)
                    now = datetime.now().astimezone()
                    offset = now.utcoffset()
                    hours = offset.total_seconds() / 3600 if offset else 0
                    entered_post = True
                    response = await self._client.post(
                        "/goform/goform_set_cmd_process",
                        data={
                            "isTest": "false",
                            "goformId": "SEND_SMS",
                            "notCallback": "true",
                            "Number": sms.destination.value,
                            "sms_time": now.strftime("%y;%m;%d;%H;%M;%S;") + f"{hours:+g}",
                            "MessageBody": sms.text.encode("utf-16-be").hex().upper(),
                            "ID": "-1",
                            "encode_type": "GSM7_default" if sms.encoding is SmsEncoding.GSM7 else "UNICODE",
                        },
                    )
                    if response.status_code in (401, 403):
                        return result(SubmissionOutcome.REJECTED, SubmissionReason.AUTH_REQUIRED)
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict):
                        return result(SubmissionOutcome.UNKNOWN, SubmissionReason.INVALID_RESPONSE)
                    if data.get("result") in ("failure", "fail"):
                        return result(SubmissionOutcome.REJECTED, SubmissionReason.DEVICE_REJECTED)
                    if data.get("result") != "success":
                        return result(SubmissionOutcome.UNKNOWN, SubmissionReason.INVALID_RESPONSE)
                    while True:
                        await asyncio.sleep(self._settings.send_poll_interval_seconds)
                        response = await self._client.get(
                            "/goform/goform_get_cmd_process",
                            params={
                                "isTest": "false",
                                "cmd": "sms_cmd_status_info",
                                "sms_cmd": 4,
                            },
                        )
                        response.raise_for_status()
                        data = response.json()
                        state = data.get("sms_cmd_status_result") if isinstance(data, dict) else None
                        if state == "3":
                            return result(SubmissionOutcome.ACCEPTED)
                        if state == "2":
                            return result(SubmissionOutcome.REJECTED, SubmissionReason.DEVICE_REJECTED)
                        if state not in ("0", "1"):
                            return result(SubmissionOutcome.UNKNOWN, SubmissionReason.INVALID_RESPONSE)
        except asyncio.CancelledError:
            if entered_post:
                self._uncertain = True
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # After entering POST, retain uncertainty even for connection errors.
            return result(
                SubmissionOutcome.UNKNOWN if entered_post else SubmissionOutcome.NOT_SUBMITTED,
                SubmissionReason.TRANSPORT_ERROR,
            )
        except (TimeoutError, httpx.TimeoutException):
            return result(
                SubmissionOutcome.UNKNOWN if entered_post else SubmissionOutcome.NOT_SUBMITTED,
                SubmissionReason.TIMEOUT,
            )
        except httpx.HTTPError:
            return result(
                SubmissionOutcome.UNKNOWN if entered_post else SubmissionOutcome.NOT_SUBMITTED,
                SubmissionReason.TRANSPORT_ERROR,
            )
        except (ValueError, UnicodeError):
            return result(
                SubmissionOutcome.UNKNOWN if entered_post else SubmissionOutcome.NOT_SUBMITTED,
                SubmissionReason.INVALID_RESPONSE,
            )
