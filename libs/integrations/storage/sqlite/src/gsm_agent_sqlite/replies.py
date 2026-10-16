"""Durable reply queue and bounded conversation exchanges for one runtime owner."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite
from gsm_agent.application.inbox import InboxRecord
from gsm_agent.application.replies import ReplyJob, ReplyJobStatus, ReplyPolicy, ReplyState, conversation_key
from gsm_agent_core.domain.agent import ChatMessage
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import SmsDestination

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
CREATE TABLE IF NOT EXISTS reply_jobs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT UNIQUE NOT NULL,
    device_id TEXT NOT NULL, conversation_key TEXT NOT NULL, request_id TEXT UNIQUE NOT NULL,
    destination TEXT NOT NULL, state TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
    issue TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_exchanges (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT UNIQUE NOT NULL,
    conversation_key TEXT NOT NULL, user_text TEXT NOT NULL, accepted_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS conversation_scope ON conversation_exchanges(conversation_key, seq);
UPDATE reply_jobs SET state='failed', issue='interrupted_generation' WHERE state='generating';
"""


class SqliteReplyStore:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path) -> "SqliteReplyStore":
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(path, isolation_level=None)
        connection.row_factory = aiosqlite.Row
        try:
            await connection.executescript(_SCHEMA)
        except BaseException:
            await connection.close()
            raise
        return cls(connection)

    async def close(self) -> None:
        async with self._lock:
            await self._connection.close()

    @asynccontextmanager
    async def _transaction(self):
        async with self._lock:
            try:
                await self._connection.execute("BEGIN IMMEDIATE")
                yield
                await self._connection.commit()
            except BaseException:
                await asyncio.shield(self._connection.rollback())
                raise

    async def enqueue(self, record: InboxRecord, destination: SmsDestination) -> None:
        async with self._lock:
            await self._connection.execute(
                "INSERT OR IGNORE INTO reply_jobs(record_id,device_id,conversation_key,request_id,"
                "destination,state,created_at) VALUES(?,?,?,?,?,'queued',?)",
                (
                    record.id,
                    record.source.device_id.value,
                    conversation_key(record, destination),
                    str(uuid4()),
                    destination.value,
                    datetime.now(UTC).isoformat(),
                ),
            )

    async def next_job(self) -> ReplyJob | None:
        async with self._lock:
            async with self._connection.execute(
                "SELECT * FROM reply_jobs WHERE state IN ('queued','prepared','submitting') "
                "ORDER BY seq LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return ReplyJob(
            row["record_id"],
            row["conversation_key"],
            UUID(row["request_id"]),
            SmsDestination(row["destination"]),
            ReplyState(row["state"]),
            row["text"],
            row["issue"],
            datetime.fromisoformat(row["created_at"]),
        )

    async def update(
        self, record_id: str, state: ReplyState, *, text: str = "", issue: str | None = None
    ) -> None:
        async with self._lock:
            await self._connection.execute(
                "UPDATE reply_jobs SET state=?,text=?,issue=? WHERE record_id=?",
                (state.value, text, issue, record_id),
            )

    async def _prune(self, policy: ReplyPolicy) -> None:
        cutoff = (datetime.now(UTC) - timedelta(days=policy.history_retention_days)).isoformat()
        await self._connection.execute("DELETE FROM conversation_exchanges WHERE created_at<?", (cutoff,))
        await self._connection.execute(
            "UPDATE reply_jobs SET text='' WHERE created_at<? "
            "AND state NOT IN ('queued','generating','prepared','submitting')",
            (cutoff,),
        )
        async with self._connection.execute(
            "SELECT * FROM conversation_exchanges ORDER BY seq DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        totals: dict[str, tuple[int, int]] = {}
        expired = []
        for row in rows:
            count, chars = totals.get(row["conversation_key"], (0, 0))
            count += 1 + bool(row["accepted_text"])
            chars += len(row["user_text"]) + len(row["accepted_text"])
            totals[row["conversation_key"]] = count, chars
            if count > policy.history_max_messages or chars > policy.history_max_chars:
                expired.append((row["seq"],))
        await self._connection.executemany("DELETE FROM conversation_exchanges WHERE seq=?", expired)

    async def prune(self, policy: ReplyPolicy) -> None:
        async with self._transaction():
            await self._prune(policy)

    async def history(self, key: str, policy: ReplyPolicy) -> tuple[ChatMessage, ...]:
        async with self._transaction():
            await self._prune(policy)
            async with self._connection.execute(
                "SELECT user_text,accepted_text FROM conversation_exchanges "
                "WHERE conversation_key=? ORDER BY seq",
                (key,),
            ) as cursor:
                rows = await cursor.fetchall()
        messages = []
        for row in rows:
            messages.append(ChatMessage("user", row["user_text"]))
            if row["accepted_text"]:
                messages.append(ChatMessage("assistant", row["accepted_text"]))
        return tuple(messages)

    async def finish(
        self,
        job: ReplyJob,
        state: ReplyState,
        user_text: str,
        accepted_text: str,
        policy: ReplyPolicy,
        *,
        issue: str | None = None,
    ) -> None:
        async with self._transaction():
            await self._connection.execute(
                "UPDATE reply_jobs SET state=?,issue=?,text='' WHERE record_id=?",
                (state.value, issue, job.record_id),
            )
            if user_text:
                await self._connection.execute(
                    "INSERT OR IGNORE INTO conversation_exchanges(record_id,conversation_key,user_text,"
                    "accepted_text,created_at) VALUES(?,?,?,?,?)",
                    (
                        job.record_id,
                        job.conversation_key,
                        user_text[: policy.input_max_chars],
                        accepted_text,
                        datetime.now(UTC).isoformat(),
                    ),
                )
            await self._prune(policy)

    async def counts(self, device_id: CellularDeviceId) -> dict[str, int]:
        async with self._lock:
            async with self._connection.execute(
                "SELECT state,COUNT(*) FROM reply_jobs WHERE device_id=? GROUP BY state",
                (device_id.value,),
            ) as cursor:
                return {row[0]: row[1] for row in await cursor.fetchall()}

    async def list_jobs(
        self, device_id: CellularDeviceId, *, limit: int, offset: int
    ) -> tuple[ReplyJobStatus, ...]:
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("Reply jobs page requires limit 1–200 and a nonnegative offset")
        async with self._lock:
            async with self._connection.execute(
                "SELECT record_id,request_id,state,issue,created_at FROM reply_jobs "
                "WHERE device_id=? ORDER BY seq DESC LIMIT ? OFFSET ?",
                (device_id.value, limit, offset),
            ) as cursor:
                return tuple(
                    ReplyJobStatus(
                        row[0], UUID(row[1]), ReplyState(row[2]), row[3], datetime.fromisoformat(row[4])
                    )
                    for row in await cursor.fetchall()
                )
