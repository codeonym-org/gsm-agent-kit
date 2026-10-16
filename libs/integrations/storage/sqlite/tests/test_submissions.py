import asyncio
from uuid import uuid4

import pytest
from gsm_agent.application.commands.send_sms import SendSms, SendSmsHandler
from gsm_agent.application.submissions import (
    PartState,
    SubmissionConflictError,
    SubmissionCoordinator,
    SubmissionPolicy,
)
from gsm_agent.application.text import SmsLimits, SmsPlan
from gsm_agent_core.capabilities.catalog import SMS_SEND, CapabilityBinding, CapabilityKey, CapabilitySet
from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId, DeviceDescriptor, DeviceModel
from gsm_agent_core.domain.submission import (
    SmsDestination,
    SmsEncoding,
    SmsSendConstraints,
    SmsSubmissionResult,
    SubmissionOutcome,
    SubmissionReason,
)
from gsm_agent_sqlite import SqliteSubmissionStore

DEVICE = CellularDeviceId("device-one")
DESTINATION = SmsDestination("+212600000000")


class FakeSender:
    constraints = SmsSendConstraints()

    def __init__(self, store, outcomes=()):
        self.store = store
        self.outcomes = iter(outcomes)
        self.calls = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False

    async def submit(self, sms):
        self.calls.append(sms)
        self.entered.set()
        if self.block:
            await self.release.wait()
        outcome = next(self.outcomes, SubmissionOutcome.ACCEPTED)
        if isinstance(outcome, Exception):
            raise outcome
        return SmsSubmissionResult(
            sms.message_id,
            sms.attempt_id,
            outcome,
            SubmissionReason.TRANSPORT_ERROR if outcome is not SubmissionOutcome.ACCEPTED else None,
        )


class FakeDevice:
    device_id = DEVICE
    manifest = AdapterManifest("fictional", "0.1.0", DeviceModel("Fictional", "Sender"), (SMS_SEND.id,))

    def __init__(self, sender):
        self.capabilities = CapabilitySet(CapabilityBinding(SMS_SEND, sender))

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return self.capabilities.get(key)

    async def describe(self):
        return DeviceDescriptor(self.device_id, self.manifest)

    async def close(self):
        pass


class Directory:
    def __init__(self, sender):
        self.device = FakeDevice(sender)

    def get(self, device_id):
        assert device_id == DEVICE
        return self.device

    def devices(self):
        return (self.device,)

    def adapters(self):
        return (self.device.manifest,)


def handler(store, sender, coordinator=None, policy=None):
    return SendSmsHandler(
        Directory(sender), store, policy or SubmissionPolicy(), coordinator or SubmissionCoordinator()
    )


def command(text="word " * 45):
    return SendSms(DEVICE, uuid4(), DESTINATION, text)


async def test_intent_and_attempt_survive_restart_accepted_is_skipped_and_active_is_unknown(tmp_path):
    path = tmp_path / "submissions.db"
    request_id = uuid4()
    plan = SmsPlan(("one", "two", "three"), SmsEncoding.GSM7, False)
    store = await SqliteSubmissionStore.open(path)
    try:
        await store.create(DEVICE, request_id, DESTINATION, "digest", plan)
        first = await store.begin_attempt(DEVICE, request_id, 0)
        assert first is not None
        await store.finish_attempt(
            SmsSubmissionResult(first.message_id, first.attempt_id, SubmissionOutcome.ACCEPTED)
        )
    finally:
        await store.close()
    store = await SqliteSubmissionStore.open(path)
    try:
        assert await store.begin_attempt(DEVICE, request_id, 0) is None
        second = await store.begin_attempt(DEVICE, request_id, 1)
        assert second is not None
    finally:
        await store.close()
    store = await SqliteSubmissionStore.open(path)
    try:
        record = await store.get(DEVICE, request_id)
        assert record is not None
        assert [part.state for part in record.parts] == [
            PartState.ACCEPTED,
            PartState.UNKNOWN,
            PartState.PENDING,
        ]
        assert record.parts[1].attempts[0].reason is SubmissionReason.INTERRUPTED
        assert await store.begin_attempt(DEVICE, request_id, 1) is None
        assert await store.begin_attempt(DEVICE, request_id, 2) is None
    finally:
        await store.close()


async def test_partial_acceptance_resumes_only_known_unsent_parts_and_plan_is_immutable(tmp_path):
    path = tmp_path / "submissions.db"
    store = await SqliteSubmissionStore.open(path)
    request = command()
    sender = FakeSender(store, (SubmissionOutcome.ACCEPTED, SubmissionOutcome.NOT_SUBMITTED))
    try:
        first = await handler(store, sender).handle(request)
        assert first.accepted_parts == 1 and first.parts[1].state is PartState.NOT_SUBMITTED
        first_message = first.parts[0].message_id
        assert len(sender.calls) == 2
    finally:
        await store.close()
    store = await SqliteSubmissionStore.open(path)
    sender = FakeSender(store)
    try:
        resumed = await handler(store, sender, policy=SubmissionPolicy(SmsLimits(16, 1))).handle(request)
        assert resumed.complete and resumed.parts[0].message_id == first_message
        assert len(sender.calls) == 1
        assert len(resumed.parts[1].attempts) == 2
        assert resumed.parts[1].attempts[0].id != resumed.parts[1].attempts[1].id
        again = await handler(store, sender).handle(request)
        assert again == resumed and len(sender.calls) == 1
        with pytest.raises(SubmissionConflictError):
            await handler(store, sender).handle(
                SendSms(DEVICE, request.request_id, DESTINATION, "different input")
            )
    finally:
        await store.close()


@pytest.mark.parametrize("outcome", [SubmissionOutcome.UNKNOWN, SubmissionOutcome.REJECTED])
async def test_unknown_and_rejected_are_terminal_without_blind_retry(tmp_path, outcome):
    store = await SqliteSubmissionStore.open(tmp_path / "submissions.db")
    request = command()
    sender = FakeSender(store, (SubmissionOutcome.ACCEPTED, outcome))
    try:
        first = await handler(store, sender).handle(request)
        assert first.accepted_parts == 1 and first.blocked
        assert (await handler(store, sender).handle(request)) == first
        assert len(sender.calls) == 2
        if outcome is SubmissionOutcome.UNKNOWN:
            with pytest.raises(SubmissionConflictError, match="unresolved"):
                await handler(store, sender).handle(command("another request"))
            assert len(sender.calls) == 2
    finally:
        await store.close()


async def test_cancellation_quarantines_current_attempt_and_preserves_accepted_progress(tmp_path):
    store = await SqliteSubmissionStore.open(tmp_path / "submissions.db")
    sender = FakeSender(store)
    sender.block = True
    request = command("hello")
    task = asyncio.create_task(handler(store, sender).handle(request))
    try:
        await asyncio.wait_for(sender.entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        record = await store.get(DEVICE, request.request_id)
        assert record is not None and record.parts[0].state is PartState.UNKNOWN
        assert (await handler(store, sender).handle(request)).blocked
        assert len(sender.calls) == 1
    finally:
        await store.close()


async def test_cancelled_or_timed_out_waiter_cannot_quarantine_the_lock_owner(tmp_path):
    store = await SqliteSubmissionStore.open(tmp_path / "submissions.db")
    sender = FakeSender(store)
    sender.block = True
    coordinator = SubmissionCoordinator()
    request = command("hello")
    owner = asyncio.create_task(handler(store, sender, coordinator).handle(request))
    try:
        await asyncio.wait_for(sender.entered.wait(), 2)
        waiting = await handler(store, sender, coordinator, SubmissionPolicy(timeout_seconds=0.01)).handle(
            request
        )
        assert waiting.parts[0].state is PartState.IN_PROGRESS
        waiter = asyncio.create_task(handler(store, sender, coordinator).handle(request))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        sender.release.set()
        assert (await owner).complete
        assert len(sender.calls) == 1
    finally:
        if not owner.done():
            owner.cancel()
        await store.close()


async def test_unexpected_adapter_failure_is_persisted_as_unknown(tmp_path):
    store = await SqliteSubmissionStore.open(tmp_path / "submissions.db")
    sender = FakeSender(store, (RuntimeError("fictional adapter failure"),))
    try:
        result = await handler(store, sender).handle(command("hello"))
        assert result.parts[0].state is PartState.UNKNOWN
        assert result.parts[0].attempts[0].reason is SubmissionReason.ADAPTER_ERROR
    finally:
        await store.close()


async def test_command_deadline_returns_durable_unknown_progress_without_retry(tmp_path):
    store = await SqliteSubmissionStore.open(tmp_path / "submissions.db")
    sender = FakeSender(store)
    sender.block = True
    request = command("hello")
    try:
        result = await handler(store, sender, policy=SubmissionPolicy(timeout_seconds=1)).handle(request)
        assert result.blocked and result.parts[0].state is PartState.UNKNOWN
        assert result.parts[0].attempts[0].reason is SubmissionReason.INTERRUPTED
        assert (await handler(store, sender).handle(request)) == result and len(sender.calls) == 1
    finally:
        await store.close()


async def test_outgoing_request_scope_separates_two_logical_devices(tmp_path):
    store = await SqliteSubmissionStore.open(tmp_path / "submissions.db")
    request_id = uuid4()
    other = CellularDeviceId("device-two")
    plan = SmsPlan(("one",), SmsEncoding.GSM7, False)
    try:
        await store.create(DEVICE, request_id, DESTINATION, "digest", plan)
        await store.create(other, request_id, DESTINATION, "digest", plan)
        first = await store.begin_attempt(DEVICE, request_id, 0)
        assert first is not None
        await store.interrupt(DEVICE, request_id)
        second = await store.begin_attempt(other, request_id, 0)
        assert second is not None and first.message_id != second.message_id
    finally:
        await store.close()
