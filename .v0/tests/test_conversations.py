import sqlite3

from gsm_agent.domain.agent import ChatMessage
from gsm_agent.domain.sms import MessageState, SmsMessage
from gsm_agent.domain.sms_text import MemoryLimits
from gsm_agent.infra.persistence.sqlite_inbox import SqliteInbox


async def test_history_caps_retry_dedup_and_excludes_later_turns(tmp_path):
    store = await SqliteInbox.open(tmp_path / "inbox.db")
    try:
        await store.remember("a", "1", ChatMessage("user", "one"))
        await store.remember("a", "1", ChatMessage("user", "one"))
        await store.remember("a", "1", ChatMessage("assistant", "two"))
        await store.remember("a", "2", ChatMessage("user", "three"))
        await store.remember("b", "3", ChatMessage("user", "private"))
        assert await store.history("a", MemoryLimits(), through_key="1") == (ChatMessage("user", "one"),)
        assert await store.history("a", MemoryLimits(max_messages=2)) == (
            ChatMessage("assistant", "two"),
            ChatMessage("user", "three"),
        )
        assert await store.history("a", MemoryLimits(max_chars=5)) == (ChatMessage("user", "three"),)
        assert await store.history("a", MemoryLimits(max_chars=2)) == (ChatMessage("user", "th"),)
    finally:
        await store.close()


async def test_upgrade_existing_database_preserves_confirmed_memory(tmp_path):
    path = tmp_path / "legacy.db"
    message = SmsMessage("1", "+212600000000", "hello", "t1")
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE inbox (
            key TEXT PRIMARY KEY, modem_id TEXT NOT NULL, sender TEXT NOT NULL,
            content TEXT NOT NULL, timestamp TEXT NOT NULL, state TEXT NOT NULL,
            reply TEXT, attempts INTEGER NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL
        )""")
        connection.execute(
            "INSERT INTO inbox VALUES(?,?,?,?,?,?,?,0,NULL,?)",
            (message.key, "1", message.sender, "hello", "t1", "sent", "hi", "t1"),
        )
    for _ in range(2):
        store = await SqliteInbox.open(path)
        try:
            assert await store.history(message.sender, MemoryLimits()) == (
                ChatMessage("user", "hello"),
                ChatMessage("assistant", "hi"),
            )
            record = await store.get(message.key)
            assert record.state == MessageState.SENT
            assert record.reply_parts == ()
        finally:
            await store.close()
