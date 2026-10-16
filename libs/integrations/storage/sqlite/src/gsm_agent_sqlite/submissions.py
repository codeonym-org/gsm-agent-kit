"""Persist intent and attempts before device I/O; interrupted attempts stay uncertain."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite
from gsm_agent.application.submissions import (
    PartState,
    SubmissionAttempt,
    SubmissionConflictError,
    SubmissionPart,
    SubmissionRecord,
)
from gsm_agent.application.text import SmsPlan
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import (
    PreparedSms,
    SmsDestination,
    SmsEncoding,
    SmsSubmissionResult,
    SubmissionOutcome,
    SubmissionReason,
)

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sms_requests (
    device_id TEXT NOT NULL, request_id TEXT NOT NULL, destination TEXT NOT NULL,
    digest TEXT NOT NULL, truncated INTEGER NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY(device_id,request_id)
);
CREATE TABLE IF NOT EXISTS sms_parts (
    message_id TEXT PRIMARY KEY, device_id TEXT NOT NULL, request_id TEXT NOT NULL,
    part_index INTEGER NOT NULL, text TEXT NOT NULL, encoding TEXT NOT NULL, state TEXT NOT NULL,
    UNIQUE(device_id,request_id,part_index),
    FOREIGN KEY(device_id,request_id) REFERENCES sms_requests(device_id,request_id)
);
CREATE TABLE IF NOT EXISTS sms_attempts (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id TEXT NOT NULL UNIQUE,
    message_id TEXT NOT NULL REFERENCES sms_parts(message_id),
    outcome TEXT, reason TEXT, provider_reference TEXT, started_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sms_attempt_message ON sms_attempts(message_id,seq);
"""


class SqliteSubmissionStore:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path) -> "SqliteSubmissionStore":
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(path, isolation_level=None)
        connection.row_factory = aiosqlite.Row
        try:
            await connection.executescript(_SCHEMA)
            store = cls(connection)
            # One runtime owns a device/ledger. Never recover an interrupted attempt as pending.
            async with store._transaction():
                await connection.execute(
                    "UPDATE sms_attempts SET outcome='unknown',reason='interrupted' WHERE outcome IS NULL"
                )
                await connection.execute("UPDATE sms_parts SET state='unknown' WHERE state='in_progress'")
            return store
        except BaseException:
            await connection.close()
            raise

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        async with self._lock:
            try:
                await self._connection.execute("BEGIN IMMEDIATE")
                yield
                await self._connection.commit()
            except BaseException:
                await asyncio.shield(self._connection.rollback())
                raise

    async def close(self) -> None:
        async with self._lock:
            await self._connection.close()

    async def _one(self, sql: str, params: tuple) -> aiosqlite.Row | None:
        async with self._connection.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def create(
        self,
        device_id: CellularDeviceId,
        request_id: UUID,
        destination: SmsDestination,
        digest: str,
        plan: SmsPlan,
    ) -> SubmissionRecord:
        async with self._transaction():
            existing = await self._read(device_id, request_id)
            if existing is not None:
                if existing.request_digest != digest:
                    raise SubmissionConflictError("Request ID already belongs to different SMS input")
                return existing
            if not plan.parts:
                raise ValueError("Submission plan must contain parts")
            await self._connection.execute(
                "INSERT INTO sms_requests VALUES(?,?,?,?,?,?)",
                (
                    device_id.value,
                    str(request_id),
                    destination.value,
                    digest,
                    plan.truncated,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await self._connection.executemany(
                "INSERT INTO sms_parts VALUES(?,?,?,?,?,?,?)",
                [
                    (
                        uuid4().hex,
                        device_id.value,
                        str(request_id),
                        index,
                        text,
                        plan.encoding.value,
                        "pending",
                    )
                    for index, text in enumerate(plan.parts)
                ],
            )
            result = await self._read(device_id, request_id)
            assert result is not None
            return result

    async def get(self, device_id: CellularDeviceId, request_id: UUID) -> SubmissionRecord | None:
        async with self._lock:
            return await self._read(device_id, request_id)

    async def _read(self, device_id: CellularDeviceId, request_id: UUID) -> SubmissionRecord | None:
        request = await self._one(
            "SELECT * FROM sms_requests WHERE device_id=? AND request_id=?",
            (device_id.value, str(request_id)),
        )
        if request is None:
            return None
        async with self._connection.execute(
            "SELECT * FROM sms_parts WHERE device_id=? AND request_id=? ORDER BY part_index",
            (device_id.value, str(request_id)),
        ) as cursor:
            parts = await cursor.fetchall()
        results = []
        for part in parts:
            async with self._connection.execute(
                "SELECT * FROM sms_attempts WHERE message_id=? ORDER BY seq", (part["message_id"],)
            ) as cursor:
                attempts = tuple(
                    SubmissionAttempt(
                        row["attempt_id"],
                        SubmissionOutcome(row["outcome"]) if row["outcome"] else None,
                        SubmissionReason(row["reason"]) if row["reason"] else None,
                        row["provider_reference"],
                        datetime.fromisoformat(row["started_at"]),
                    )
                    for row in await cursor.fetchall()
                )
            results.append(
                SubmissionPart(
                    part["message_id"],
                    part["part_index"],
                    part["text"],
                    SmsEncoding(part["encoding"]),
                    PartState(part["state"]),
                    attempts,
                )
            )
        return SubmissionRecord(
            device_id,
            request_id,
            SmsDestination(request["destination"]),
            request["digest"],
            bool(request["truncated"]),
            datetime.fromisoformat(request["created_at"]),
            tuple(results),
        )

    async def begin_attempt(
        self, device_id: CellularDeviceId, request_id: UUID, index: int
    ) -> PreparedSms | None:
        async with self._transaction():
            record = await self._read(device_id, request_id)
            if record is None or record.blocked:
                return None
            unresolved = await self._one(
                "SELECT 1 FROM sms_parts WHERE device_id=? AND state IN ('in_progress','unknown') LIMIT 1",
                (device_id.value,),
            )
            if unresolved is not None:
                raise SubmissionConflictError("Device has an unresolved submission; inspect its ledger")
            part = next((part for part in record.parts if part.index == index), None)
            if part is None or part.state not in (PartState.PENDING, PartState.NOT_SUBMITTED):
                return None
            # Preserve order; a later part cannot jump a previously unaccepted part.
            if any(previous.state is not PartState.ACCEPTED for previous in record.parts[:index]):
                return None
            attempt_id = uuid4().hex
            await self._connection.execute(
                "UPDATE sms_parts SET state='in_progress' WHERE message_id=?", (part.message_id,)
            )
            await self._connection.execute(
                "INSERT INTO sms_attempts(attempt_id,message_id,started_at) VALUES(?,?,?)",
                (attempt_id, part.message_id, datetime.now(UTC).isoformat()),
            )
            return PreparedSms(part.message_id, attempt_id, record.destination, part.text, part.encoding)

    async def finish_attempt(self, result: SmsSubmissionResult) -> None:
        async with self._transaction():
            attempt = await self._one(
                "SELECT * FROM sms_attempts WHERE attempt_id=? AND message_id=?",
                (result.attempt_id, result.message_id),
            )
            if attempt is None or attempt["outcome"] is not None:
                raise ValueError("Only an active attempt can finish")
            await self._connection.execute(
                "UPDATE sms_attempts SET outcome=?,reason=?,provider_reference=? WHERE attempt_id=?",
                (
                    result.outcome.value,
                    result.reason.value if result.reason else None,
                    result.provider_reference,
                    result.attempt_id,
                ),
            )
            await self._connection.execute(
                "UPDATE sms_parts SET state=? WHERE message_id=?", (result.outcome.value, result.message_id)
            )

    async def interrupt(self, device_id: CellularDeviceId, request_id: UUID) -> None:
        async with self._transaction():
            await self._connection.execute(
                "UPDATE sms_attempts SET outcome='unknown',reason='interrupted' WHERE outcome IS NULL "
                "AND message_id IN (SELECT message_id FROM sms_parts WHERE device_id=? AND request_id=?)",
                (device_id.value, str(request_id)),
            )
            await self._connection.execute(
                "UPDATE sms_parts SET state='unknown' WHERE device_id=? AND request_id=? "
                "AND state='in_progress'",
                (device_id.value, str(request_id)),
            )
