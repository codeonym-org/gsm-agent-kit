from gsm_agent.domain.sms import MessageState, SmsMessage
from gsm_agent.infra.persistence.sqlite_inbox import SqliteInbox


async def test_baseline_dedup_partial_and_reused_id(tmp_path):
    store = await SqliteInbox.open(tmp_path / "inbox.db")
    old = SmsMessage("1", "+212600000000", "old", "t1")
    partial = SmsMessage("2", "+212600000000", "part", "t2", complete=False)
    try:
        assert await store.ingest([old, partial], True) == 2
        assert await store.work() == []
        completed_old = SmsMessage("2", partial.sender, "part complete", "t2")
        assert await store.ingest([old, completed_old], True) == 0
        new_partial = SmsMessage("3", old.sender, "new", "t3", complete=False)
        assert await store.ingest([new_partial], True) == 0
        new_complete = SmsMessage("3", old.sender, "new complete", "t3")
        reused = SmsMessage("1", old.sender, "new id reused", "t4")
        assert await store.ingest([new_complete, reused], True) == 2
        assert await store.ingest([new_complete, reused], True) == 0
        assert len(await store.work()) == 2
    finally:
        await store.close()


async def test_restart_recovers_generation_but_quarantines_sends(tmp_path):
    path = tmp_path / "inbox.db"
    store = await SqliteInbox.open(path)
    await store.ingest([], True)
    a = SmsMessage("1", "+212600000000", "a", "t1")
    b = SmsMessage("2", a.sender, "b", "t2")
    await store.ingest([a, b], True)
    assert await store.claim(a.key, MessageState.PENDING, MessageState.PROCESSING)
    assert not await store.claim(a.key, MessageState.PENDING, MessageState.PROCESSING)
    await store.update(b.key, MessageState.SENDING, reply="hello")
    await store.close()
    recovered = await SqliteInbox.open(path)
    try:
        assert (await recovered.get(a.key)).state == MessageState.PENDING
        assert (await recovered.get(b.key)).state == MessageState.UNCERTAIN
        assert (await recovered.get(b.key)).reply == "hello"
    finally:
        await recovered.close()
