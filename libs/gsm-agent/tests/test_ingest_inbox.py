import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from gsm_agent.application.commands.ingest_inbox import IngestInbox, IngestInboxHandler
from gsm_agent.application.errors import UnsupportedCapabilityError
from gsm_agent.application.events.sms_received import SmsReceived
from gsm_agent.application.inbox import InboxDeadlineError, InboxPolicy, IngestionCoordinator
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.queries.inbox import ListStoredMessages, ListStoredMessagesHandler
from gsm_agent_core.capabilities.catalog import (
    SMS_INBOX_READ,
    CapabilityBinding,
    CapabilityKey,
    CapabilitySet,
)
from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId, DeviceDescriptor, DeviceModel
from gsm_agent_core.domain.sms import InboxItem, InboxReadError, InboxSnapshot, InboxSource, SmsAddress
from gsm_agent_sqlite import SqliteInboxStore
from mediary.cqrs import Event

DEVICE = CellularDeviceId("device")


class FakeDevice:
    device_id = DEVICE
    manifest = AdapterManifest("fake", "0.1.0", DeviceModel("Fictional", "Inbox"), (SMS_INBOX_READ.id,))

    def __init__(self):
        self.items: tuple[InboxItem, ...] = ()
        self.calls = 0
        self.source = InboxSource(DEVICE, "storage-one", "device-database")
        self.capabilities = CapabilitySet(CapabilityBinding(SMS_INBOX_READ, self))

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return self.capabilities.get(key)

    async def describe(self):
        return DeviceDescriptor(self.device_id, self.manifest)

    async def close(self):
        pass

    async def scan(self) -> InboxSnapshot:
        self.calls += 1
        await asyncio.sleep(0)
        now = datetime.now(UTC)
        return InboxSnapshot(self.source, "sim-one", now, now, self.items)


class Devices:
    def __init__(self, device):
        self.device = device

    def adapters(self):
        return (self.device.manifest,)

    def devices(self):
        return (self.device,)

    def get(self, device_id):
        assert device_id == self.device.device_id
        return self.device


class Publisher:
    def __init__(self, store: InboxStore):
        self.store = store
        self.events = []
        self.fail = False

    async def publish(self, event: Event, /) -> None:
        assert isinstance(event, SmsReceived)
        records = await self.store.list_records(DEVICE, limit=200, offset=0)
        assert event.record_id in {record.id for record in records if record.replyable}
        self.events.append(event)
        if self.fail:
            raise RuntimeError("injected handler failure")


def make_handler(device, store, publisher, coordinator=None, timeout: float = 5):
    directory: DeviceDirectory = Devices(device)
    return IngestInboxHandler(
        directory, store, publisher, coordinator or IngestionCoordinator(), InboxPolicy(timeout)
    )


async def test_overlapping_ingestions_dispatch_once_and_events_observe_committed_state(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    device = FakeDevice()
    publisher = Publisher(store)
    handler = make_handler(device, store, publisher)
    try:
        assert (await handler.handle(IngestInbox(DEVICE))).baselined
        device.items = (InboxItem("1", SmsAddress.from_sender("+212600000000"), "Hello", "t1", True),)
        results = await asyncio.gather(*(handler.handle(IngestInbox(DEVICE)) for _ in range(3)))
        assert sum(result.queued for result in results) == 1
        assert len(publisher.events) == 1
        assert await store.pending_events(DEVICE) == ()
    finally:
        await store.close()


async def test_failed_event_is_durable_and_redelivered_with_same_id_after_restart(tmp_path):
    path = tmp_path / "inbox.db"
    store = await SqliteInboxStore.open(path)
    device = FakeDevice()
    publisher = Publisher(store)
    handler = make_handler(device, store, publisher)
    try:
        await handler.handle(IngestInbox(DEVICE))
        device.items = (InboxItem("1", SmsAddress.from_sender("+212600000000"), "Hello", "t1", True),)
        publisher.fail = True
        with pytest.raises(RuntimeError, match="handler failure"):
            await handler.handle(IngestInbox(DEVICE))
        failed_id = publisher.events[0].record_id
        assert await store.pending_events(DEVICE) == (failed_id,)
    finally:
        await store.close()
    store = await SqliteInboxStore.open(path)
    publisher = Publisher(store)
    try:
        assert (await make_handler(device, store, publisher).handle(IngestInbox(DEVICE))).queued == 0
        assert publisher.events[0].record_id == failed_id
        assert await store.pending_events(DEVICE) == ()
    finally:
        await store.close()


async def test_deadline_includes_waiting_for_workflow_lock_without_scanning(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    device, coordinator = FakeDevice(), IngestionCoordinator()
    try:
        handler = make_handler(device, store, Publisher(store), coordinator, timeout=0.01)
        async with coordinator.lock(DEVICE):
            with pytest.raises(InboxDeadlineError):
                await handler.handle(IngestInbox(DEVICE))
        assert device.calls == 0
        assert await store.list_records(DEVICE, limit=50, offset=0) == ()
    finally:
        await store.close()


async def test_wrong_source_is_rejected_without_establishing_a_baseline(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    device = FakeDevice()
    device.source = replace(device.source, device_id=CellularDeviceId("wrong-device"))
    try:
        handler = make_handler(device, store, Publisher(store))
        with pytest.raises(InboxReadError):
            await handler.handle(IngestInbox(DEVICE))
        device.source = replace(device.source, device_id=DEVICE)
        assert (await handler.handle(IngestInbox(DEVICE))).baselined
    finally:
        await store.close()


async def test_unsupported_capability_never_scans_or_changes_the_store(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    device = FakeDevice()
    device.capabilities = CapabilitySet()
    try:
        with pytest.raises(UnsupportedCapabilityError):
            await make_handler(device, store, Publisher(store)).handle(IngestInbox(DEVICE))
        assert device.calls == 0
    finally:
        await store.close()


async def test_stored_messages_query_never_scans_hardware(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    device = FakeDevice()
    try:
        result = await ListStoredMessagesHandler(Devices(device), store).handle(ListStoredMessages(DEVICE))
        assert result == () and device.calls == 0
    finally:
        await store.close()


async def test_failed_scan_does_not_baseline_or_create_partial_records(tmp_path, monkeypatch):
    from gsm_agent_core.domain.devices import DeviceReadIssue

    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    device = FakeDevice()
    scan = device.scan

    async def fail():
        raise InboxReadError(DeviceReadIssue.INVALID_RESPONSE)

    monkeypatch.setattr(device, "scan", fail)
    try:
        handler = make_handler(device, store, Publisher(store))
        with pytest.raises(InboxReadError):
            await handler.handle(IngestInbox(DEVICE))
        assert await store.list_records(DEVICE, limit=50, offset=0) == ()
        monkeypatch.setattr(device, "scan", scan)
        assert (await handler.handle(IngestInbox(DEVICE))).baselined
    finally:
        await store.close()
