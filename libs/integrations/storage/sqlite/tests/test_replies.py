from dataclasses import replace
from datetime import UTC, datetime

import aiosqlite
import pytest
from gsm_agent.application.inbox import InboxRecord
from gsm_agent.application.replies import ReplyPolicy, ReplyState, conversation_key, reply_destination
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxItem, InboxSource, SmsAddress
from gsm_agent_core.domain.submission import SmsDestination
from gsm_agent_sqlite import SqliteReplyStore


def record(record_id="one", sender="+212600000000", device="first", subscription="sim-one"):
    return InboxRecord(
        record_id,
        InboxSource(CellularDeviceId(device), "storage-one", "inbox"),
        InboxItem(record_id, SmsAddress.from_sender(sender), "Question", "fixture-date", True),
        subscription,
        False,
        False,
        datetime.now(UTC),
    )


def test_normalized_correspondent_is_scoped_by_device_and_sim():
    first = record()
    destination = reply_destination(first, None)
    assert destination is not None
    assert destination == SmsDestination("+212600000000")
    local = record(sender="0600000000")
    assert reply_destination(local, None) is None
    assert reply_destination(local, "MA") == destination
    assert reply_destination(record(sender="00212600000000"), None) == destination
    assert conversation_key(first, destination) == conversation_key(local, destination)
    assert conversation_key(first, destination) != conversation_key(record(device="second"), destination)
    assert conversation_key(first, destination) != conversation_key(
        record(subscription="sim-two"), destination
    )
    for sender in ("Carrier", "120", "0612", "+123", "0600000000 ext 1"):
        assert reply_destination(record(sender=sender), "MA") is None


async def test_durable_dedup_retention_and_recovery_are_conservative(tmp_path):
    path = tmp_path / "conversations.db"
    store = await SqliteReplyStore.open(path)
    policy = ReplyPolicy(history_max_messages=4, history_max_chars=100)
    destination = SmsDestination("+212600000000")
    key = conversation_key(record(), destination)
    try:
        for index in range(3):
            incoming = record(str(index))
            await store.enqueue(incoming, destination)
            await store.enqueue(incoming, destination)
            job = await store.next_job()
            assert job is not None
            await store.finish(job, ReplyState.COMPLETED, "Question " + str(index), "Accepted", policy)
        history = await store.history(key, policy)
        assert len(history) == 4 and history[0].content == "Question 1"
        assert len(await store.history(key, replace(policy, history_max_chars=20))) == 2
        await store.enqueue(record("crashed"), destination)
        await store.update("crashed", ReplyState.GENERATING)
    finally:
        await store.close()
    store = await SqliteReplyStore.open(path)
    try:
        assert await store.next_job() is None
        assert (await store.counts(CellularDeviceId("first")))["failed"] == 1
        async with aiosqlite.connect(path) as connection:
            await connection.execute(
                "UPDATE conversation_exchanges SET created_at='2000-01-01T00:00:00+00:00'"
            )
            await connection.commit()
        assert await store.history(key, policy) == ()
        async with aiosqlite.connect(path) as connection:
            async with connection.execute("SELECT COUNT(*) FROM conversation_exchanges") as cursor:
                row = await cursor.fetchone()
                assert row is not None and row[0] == 0
    finally:
        await store.close()


async def test_finish_transaction_failure_cannot_mark_done_without_history(tmp_path, monkeypatch):
    store = await SqliteReplyStore.open(tmp_path / "history.db")
    incoming, destination = record(), SmsDestination("+212600000000")
    await store.enqueue(incoming, destination)
    job = await store.next_job()
    assert job is not None
    original = store._prune

    async def fail(policy):
        raise RuntimeError("injected transaction failure")

    monkeypatch.setattr(store, "_prune", fail)
    try:
        with pytest.raises(RuntimeError):
            await store.finish(job, ReplyState.COMPLETED, "Question", "Accepted", ReplyPolicy())
        assert await store.next_job() == job
        monkeypatch.setattr(store, "_prune", original)
        assert await store.history(job.conversation_key, ReplyPolicy()) == ()
    finally:
        await store.close()


async def test_other_devices_and_sim_generations_never_enter_same_history(tmp_path):
    store = await SqliteReplyStore.open(tmp_path / "separate.db")
    destination = SmsDestination("+212600000000")
    policy = ReplyPolicy()
    try:
        incoming = (record("one"), record("two", device="second"), record("three", subscription="sim-two"))
        for item in incoming:
            await store.enqueue(item, destination)
            job = await store.next_job()
            assert job is not None
            await store.finish(job, ReplyState.COMPLETED, item.id, "Answer " + item.id, policy)
        for item in incoming:
            history = await store.history(conversation_key(item, destination), policy)
            assert [msg.content for msg in history] == [item.id, "Answer " + item.id]
    finally:
        await store.close()
