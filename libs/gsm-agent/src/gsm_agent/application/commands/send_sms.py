import asyncio
from dataclasses import dataclass
from uuid import UUID

from gsm_agent_core.capabilities.catalog import SMS_SEND
from gsm_agent_core.capabilities.sending import SmsSender
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import (
    SmsDestination,
    SmsSubmissionResult,
    SubmissionOutcome,
    SubmissionReason,
)
from mediary.cqrs import Command, command, command_handler

from gsm_agent.application.errors import UnsupportedCapabilityError
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.submissions import SubmissionStore
from gsm_agent.application.submissions import (
    InvalidSmsError,
    SubmissionConflictError,
    SubmissionCoordinator,
    SubmissionDeadlineError,
    SubmissionPolicy,
    SubmissionRecord,
    request_digest,
)
from gsm_agent.application.text import prepare_sms


@command
@dataclass(frozen=True)
class SendSms(Command[SubmissionRecord]):
    device_id: CellularDeviceId
    request_id: UUID
    destination: SmsDestination
    text: str


@command_handler
class SendSmsHandler:
    def __init__(
        self,
        devices: DeviceDirectory,
        submissions: SubmissionStore,
        policy: SubmissionPolicy,
        coordinator: SubmissionCoordinator,
    ) -> None:
        self.devices, self.submissions = devices, submissions
        self.policy, self.coordinator = policy, coordinator

    async def handle(self, request: SendSms) -> SubmissionRecord:
        sender = self.devices.get(request.device_id).get(SMS_SEND)
        if sender is None:
            raise UnsupportedCapabilityError(SMS_SEND.id)
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                async with self.coordinator.lock(request.device_id):
                    try:
                        return await self._submit(request, sender)
                    except BaseException:
                        # Cleanup precedes releasing the workflow lock. A cancelled waiter
                        # must never interrupt another request that owns this lock.
                        await asyncio.shield(
                            self.submissions.interrupt(request.device_id, request.request_id)
                        )
                        raise
        except TimeoutError:
            record = await self.submissions.get(request.device_id, request.request_id)
            if record is not None:
                if record.request_digest != request_digest(request.destination, request.text):
                    raise SubmissionConflictError("Request ID already belongs to different SMS input")
                return record
            raise SubmissionDeadlineError(
                "Submission exceeded its deadline before intent was committed"
            ) from None

    async def _submit(self, request: SendSms, sender: SmsSender) -> SubmissionRecord:
        digest = request_digest(request.destination, request.text)
        record = await self.submissions.get(request.device_id, request.request_id)
        if record is not None:
            if record.request_digest != digest:
                raise SubmissionConflictError("Request ID already belongs to different SMS input")
        else:
            try:
                plan = prepare_sms(request.text, self.policy.limits, sender.constraints)
            except ValueError as exc:
                raise InvalidSmsError(str(exc)) from None
            record = await self.submissions.create(
                request.device_id, request.request_id, request.destination, digest, plan
            )
        if record.blocked:
            return record
        for part in record.parts:
            sms = await self.submissions.begin_attempt(request.device_id, request.request_id, part.index)
            if sms is None:
                continue
            try:
                result = await sender.submit(sms)
                if result.message_id != sms.message_id or result.attempt_id != sms.attempt_id:
                    result = SmsSubmissionResult(
                        sms.message_id,
                        sms.attempt_id,
                        SubmissionOutcome.UNKNOWN,
                        SubmissionReason.INVALID_RESPONSE,
                    )
            except Exception:
                result = SmsSubmissionResult(
                    sms.message_id, sms.attempt_id, SubmissionOutcome.UNKNOWN, SubmissionReason.ADAPTER_ERROR
                )
            await self.submissions.finish_attempt(result)
            if result.outcome is not SubmissionOutcome.ACCEPTED:
                break
        updated = await self.submissions.get(request.device_id, request.request_id)
        assert updated is not None
        return updated
