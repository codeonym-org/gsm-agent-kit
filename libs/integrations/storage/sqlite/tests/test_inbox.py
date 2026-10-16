import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxItem, InboxSnapshot, InboxSource, SmsAddress
from gsm_agent_sqlite import SqliteInboxStore

DEVICE = CellularDeviceId("device-one")
SOURCE = InboxSource(DEVICE, "storage-one", "device-database")
START = datetime(2026, 1, 1, tzinfo=UTC)


def item(slot="1", body="hello", date="26;01;01;12;00;00;+00", complete=True):
    return InboxItem(slot, SmsAddress.from_sender("+212600000000"), body, date, complete)


def snapshot(*items, source=SOURCE, subscription="sim-one", tick=0):
    now = START + timedelta(seconds=tick)
    return InboxSnapshot(source, subscription, now, now, tuple(items))


async def records(store, device=DEVICE):
    return await store.list_records(device, limit=200, offset=0)


async def test_each_device_baselines_independently_and_restart_deduplicates(tmp_path):
    path = tmp_path / "inbox.sqlite3"
    other = replace(SOURCE, device_id=CellularDeviceId("device-two"))
    store = await SqliteInboxStore.open(path)
    try:
        assert (await store.ingest(snapshot(item()))).baselined
        assert (await store.ingest(snapshot(item(), source=other))).baselined
        assert await store.pending_events(DEVICE) == ()
        assert await store.pending_events(other.device_id) == ()
        new = snapshot(item("2", body="new"), tick=1)
        assert (await store.ingest(new)).queued == 1
        assert (await store.ingest(new)).queued == 0
        assert len(await store.pending_events(DEVICE)) == 1
    finally:
        await store.close()
    store = await SqliteInboxStore.open(path)
    try:
        assert (await store.ingest(new)).queued == 0
        events = await store.pending_events(DEVICE)
        assert len(events) == 1
        await store.acknowledge_event(events[0])
        assert await store.pending_events(DEVICE) == ()
        assert len(await records(store)) == 2
    finally:
        await store.close()


async def test_baseline_partial_stays_backlog_but_new_partial_emits_once_on_completion(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    old = item(complete=False, body="first part")
    fresh = item("2", complete=False, body="new part")
    try:
        await store.ingest(snapshot(old))
        original_id = (await records(store))[0].id
        await store.ingest(snapshot(replace(old, body="first part completed", complete=True), fresh, tick=1))
        assert await store.pending_events(DEVICE) == ()
        assert (await records(store))[1].id == original_id
        assert (await records(store))[1].baselined
        result = await store.ingest(
            snapshot(replace(fresh, body="new part completed", complete=True), tick=2)
        )
        assert result.queued == 1
        assert len(await store.pending_events(DEVICE)) == 1
        result = await store.ingest(snapshot(fresh, tick=3))
        assert result.queued == 0
        complete = next(
            record
            for record in await records(store)
            if record.item.provider_id == "2" and record.item.complete
        )
        assert complete.replyable
    finally:
        await store.close()


async def test_reused_slot_and_same_timestamp_different_body_have_distinct_occurrences(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    try:
        await store.ingest(snapshot())
        assert (await store.ingest(snapshot(item(), tick=1))).queued == 1
        assert (await store.ingest(snapshot(item(body="another"), tick=2))).queued == 1
        assert (await store.ingest(snapshot(item(date="26;01;02;12;00;00;+00"), tick=3))).queued == 1
        assert len({record.id for record in await records(store)}) == 3
    finally:
        await store.close()


async def test_sim_change_preserves_retained_identity_and_baselines_new_subscription(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    try:
        await store.ingest(snapshot())
        await store.ingest(snapshot(item(), tick=1))
        original = (await records(store))[0]
        assert original.replyable
        changed = await store.ingest(
            snapshot(item(), item("2", body="new SIM backlog"), subscription="sim-two", tick=2)
        )
        assert changed.baselined and changed.queued == 0
        retained = next(record for record in await records(store) if record.id == original.id)
        assert retained.subscription_uncertain and not retained.replyable
        assert retained.subscription_generation == "sim-one"
        assert await store.pending_events(DEVICE) == ()
        assert (await store.ingest(snapshot(item("3"), subscription="sim-two", tick=3))).queued == 1
    finally:
        await store.close()


async def test_storage_replacement_has_new_baseline_and_quarantines_previous_work(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    replacement = replace(SOURCE, storage_generation="replacement")
    try:
        await store.ingest(snapshot())
        await store.ingest(snapshot(item(), tick=1))
        previous = (await records(store))[0]
        assert len(await store.pending_events(DEVICE)) == 1
        assert (await store.ingest(snapshot(item(), source=replacement, tick=2))).baselined
        assert len(await records(store)) == 2
        assert await store.pending_events(DEVICE) == ()
        old = next(record for record in await records(store) if record.id == previous.id)
        assert not old.replyable
    finally:
        await store.close()


async def test_overlapping_connections_commit_only_one_event_and_baseline(tmp_path):
    path = tmp_path / "shared.db"
    one, two = await SqliteInboxStore.open(path), await SqliteInboxStore.open(path)
    try:
        results = await asyncio.gather(one.ingest(snapshot()), two.ingest(snapshot()))
        assert sum(result.baselined for result in results) == 1
        results = await asyncio.gather(
            one.ingest(snapshot(item(), tick=1)), two.ingest(snapshot(item(), tick=1))
        )
        assert sum(result.queued for result in results) == 1
        assert len(await records(one)) == 1
        assert len(await two.pending_events(DEVICE)) == 1
    finally:
        await one.close()
        await two.close()


async def test_older_scan_cannot_regress_completion_or_subscription_context(tmp_path):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    try:
        await store.ingest(snapshot())
        await store.ingest(snapshot(item(), subscription="sim-two", tick=2))
        assert (await store.ingest(snapshot(item(complete=False), tick=1))).observed == 0
        assert (await records(store))[0].item.complete
        assert (await records(store))[0].subscription_generation == "sim-two"
    finally:
        await store.close()


async def test_transaction_failure_rolls_back_baseline_records_and_outbox(tmp_path, monkeypatch):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    original = store._ingest

    async def fail(snapshot):
        await original(snapshot)
        raise RuntimeError("injected failure after writes")

    monkeypatch.setattr(store, "_ingest", fail)
    try:
        with pytest.raises(RuntimeError):
            await store.ingest(snapshot(item()))
        assert await records(store) == ()
        monkeypatch.setattr(store, "_ingest", original)
        assert (await store.ingest(snapshot(item(), tick=1))).baselined
        assert await store.pending_events(DEVICE) == ()
    finally:
        await store.close()


async def test_cancellation_rolls_back_and_connection_remains_usable(tmp_path, monkeypatch):
    store = await SqliteInboxStore.open(tmp_path / "inbox.db")
    entered = asyncio.Event()
    original = store._ingest

    async def pause(snapshot):
        await original(snapshot)
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(store, "_ingest", pause)
    task = asyncio.create_task(store.ingest(snapshot(item())))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await records(store) == ()
        monkeypatch.setattr(store, "_ingest", original)
        assert (await store.ingest(snapshot(item(), tick=1))).baselined
    finally:
        await store.close()
