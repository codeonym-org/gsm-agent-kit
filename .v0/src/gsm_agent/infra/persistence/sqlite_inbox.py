import asyncio
import json
from pathlib import Path

import aiosqlite

from gsm_agent.domain.agent import ChatMessage
from gsm_agent.domain.sms import InboxRecord, MessageState, PhoneNumber, SmsMessage
from gsm_agent.domain.sms_text import MemoryLimits


class SqliteInbox:
    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path) -> "SqliteInbox":
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(path, isolation_level=None)
        connection.row_factory = aiosqlite.Row
        try:
            await connection.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA busy_timeout=5000;
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS inbox (
                    key TEXT PRIMARY KEY, modem_id TEXT NOT NULL, sender TEXT NOT NULL,
                    content TEXT NOT NULL, timestamp TEXT NOT NULL, state TEXT NOT NULL,
                    reply TEXT, attempts INTEGER NOT NULL DEFAULT 0, error TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                );
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL,
                    source_key TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    UNIQUE(thread_id, source_key, role)
                );
                CREATE INDEX IF NOT EXISTS conversation_thread ON conversation_turns(thread_id, seq);
                UPDATE inbox SET state='pending' WHERE state='processing';
                UPDATE inbox SET state='uncertain', error='InterruptedSend' WHERE state='sending';
            """)
            async with connection.execute("PRAGMA table_info(inbox)") as cursor:
                columns = {row["name"] for row in await cursor.fetchall()}
            if "reply_parts" not in columns:
                await connection.execute(
                    "ALTER TABLE inbox ADD COLUMN reply_parts TEXT NOT NULL DEFAULT '[]'"
                )
            if "sent_parts" not in columns:
                await connection.execute("ALTER TABLE inbox ADD COLUMN sent_parts INTEGER NOT NULL DEFAULT 0")
            # Preserve conversation continuity for previously confirmed sends.
            async with connection.execute(
                "SELECT * FROM inbox WHERE state='sent' AND reply IS NOT NULL ORDER BY created_at, rowid"
            ) as cursor:
                previous = await cursor.fetchall()
            for row in previous:
                try:
                    thread = PhoneNumber(row["sender"]).value
                except ValueError:
                    continue
                for role, content in (("user", row["content"]), ("assistant", row["reply"])):
                    await connection.execute(
                        "INSERT OR IGNORE INTO conversation_turns(thread_id,source_key,role,content) "
                        "VALUES(?,?,?,?)",
                        (thread, row["key"], role, content),
                    )
        except BaseException:
            await connection.close()
            raise
        return cls(connection)

    async def close(self) -> None:
        await self.connection.close()

    async def ingest(self, messages: list[SmsMessage], enabled: bool) -> int:
        async with self._lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                async with self.connection.execute(
                    "SELECT value FROM metadata WHERE key='baselined'"
                ) as cursor:
                    first = await cursor.fetchone() is None
                state = (
                    MessageState.BASELINED
                    if first
                    else (MessageState.PENDING if enabled else MessageState.OBSERVED)
                )
                added = 0
                for message in messages:
                    # Baseline incomplete messages too. Their identity below also
                    # excludes completed versions after their content changes.
                    if not first and not message.complete:
                        continue
                    if not first:
                        async with self.connection.execute(
                            "SELECT 1 FROM inbox WHERE modem_id=? AND sender=? "
                            "AND timestamp=? AND state='baselined'",
                            (message.modem_id, message.sender, message.timestamp),
                        ) as cursor:
                            if await cursor.fetchone() is not None:
                                continue
                    async with self.connection.execute(
                        "INSERT OR IGNORE INTO inbox(key,modem_id,sender,content,timestamp,state) "
                        "VALUES(?,?,?,?,?,?)",
                        (
                            message.key,
                            message.modem_id,
                            message.sender,
                            message.content,
                            message.timestamp,
                            state,
                        ),
                    ) as cursor:
                        added += cursor.rowcount
                if first:
                    await self.connection.execute("INSERT INTO metadata VALUES('baselined','1')")
                await self.connection.commit()
                return added
            except BaseException:
                await self.connection.rollback()
                raise

    @staticmethod
    def _record(row: aiosqlite.Row) -> InboxRecord:
        return InboxRecord(
            SmsMessage(row["modem_id"], row["sender"], row["content"], row["timestamp"]),
            MessageState(row["state"]),
            row["reply"],
            row["attempts"],
            row["error"],
            tuple(json.loads(row["reply_parts"])),
            row["sent_parts"],
        )

    async def work(self) -> list[InboxRecord]:
        async with self._lock:
            async with self.connection.execute(
                "SELECT * FROM inbox WHERE state IN ('pending','planned') "
                "ORDER BY timestamp, created_at, rowid LIMIT 100"
            ) as cursor:
                return [self._record(row) for row in await cursor.fetchall()]

    async def get(self, key: str) -> InboxRecord | None:
        async with self._lock:
            async with self.connection.execute("SELECT * FROM inbox WHERE key=?", (key,)) as cursor:
                row = await cursor.fetchone()
                return self._record(row) if row else None

    async def claim(self, key: str, expected: MessageState, state: MessageState) -> bool:
        async with self._lock:
            async with self.connection.execute(
                "UPDATE inbox SET state=? WHERE key=? AND state=?", (state, key, expected)
            ) as cursor:
                return cursor.rowcount == 1

    async def update(
        self,
        key: str,
        state: MessageState,
        *,
        reply: str | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
        reply_parts: tuple[str, ...] | None = None,
    ) -> None:
        async with self._lock:
            await self.connection.execute(
                "UPDATE inbox SET state=?, reply=COALESCE(?,reply), error=?, attempts=attempts+?, "
                "reply_parts=COALESCE(?,reply_parts) WHERE key=?",
                (
                    state,
                    reply,
                    error,
                    int(increment_attempts),
                    json.dumps(reply_parts) if reply_parts is not None else None,
                    key,
                ),
            )

    async def remember(self, thread_id: str, source_key: str, message: ChatMessage) -> None:
        async with self._lock:
            await self._remember(thread_id, source_key, message)

    async def _remember(self, thread_id: str, source_key: str, message: ChatMessage) -> None:
        await self.connection.execute(
            "INSERT INTO conversation_turns(thread_id,source_key,role,content) VALUES(?,?,?,?) "
            "ON CONFLICT(thread_id,source_key,role) DO UPDATE SET content=excluded.content",
            (thread_id, source_key, message.role, message.content),
        )

    async def history(
        self, thread_id: str, limits: MemoryLimits, *, through_key: str | None = None
    ) -> tuple[ChatMessage, ...]:
        async with self._lock:
            cutoff = ""
            params: tuple = (thread_id, limits.max_messages)
            if through_key is not None:
                cutoff = (
                    " AND seq <= (SELECT seq FROM conversation_turns "
                    "WHERE thread_id=? AND source_key=? AND role='user')"
                )
                params = (thread_id, thread_id, through_key, limits.max_messages)
            async with self.connection.execute(
                "SELECT role,content FROM conversation_turns WHERE thread_id=?"
                + cutoff
                + " ORDER BY seq DESC LIMIT ?",
                params,
            ) as cursor:
                rows = await cursor.fetchall()
        messages = []
        remaining = limits.max_chars
        for row in rows:
            content = row["content"]
            if len(content) > remaining:
                if not messages:
                    messages.append(ChatMessage(row["role"], content[:remaining]))
                break
            messages.append(ChatMessage(row["role"], content))
            remaining -= len(content)
        return tuple(reversed(messages))

    async def confirm_part(self, key: str, thread_id: str, text: str) -> None:
        async with self._lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                async with self.connection.execute(
                    "UPDATE inbox SET sent_parts=sent_parts+1 WHERE key=? AND state='sending'",
                    (key,),
                ) as cursor:
                    if cursor.rowcount != 1:
                        raise ValueError("Can only confirm a part of an active send")
                await self._remember(thread_id, key, ChatMessage("assistant", text))
                await self.connection.commit()
            except BaseException:
                await self.connection.rollback()
                raise

    async def list_records(self, limit: int) -> list[InboxRecord]:
        async with self._lock:
            async with self.connection.execute(
                "SELECT * FROM inbox ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ) as cursor:
                return [self._record(row) for row in await cursor.fetchall()]
