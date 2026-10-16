"""SQLite ledger and transactional outbox. Device unread flags are never consulted."""

import asyncio
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite
from gsm_agent.application.inbox import InboxRecord, IngestResult
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.sms import InboxItem, InboxSnapshot, InboxSource, SmsAddress, SmsAddressKind

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
CREATE TABLE IF NOT EXISTS inbox_baselines (
    source_key TEXT NOT NULL, subscription_generation TEXT NOT NULL,
    PRIMARY KEY(source_key, subscription_generation)
);
CREATE TABLE IF NOT EXISTS inbox_sources (
    source_key TEXT PRIMARY KEY, last_started_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox_records (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
    source_key TEXT NOT NULL, device_id TEXT NOT NULL, storage_generation TEXT NOT NULL,
    storage TEXT NOT NULL, subscription_generation TEXT NOT NULL,
    subscription_uncertain INTEGER NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL, provider_id TEXT NOT NULL, sender TEXT NOT NULL, sender_kind TEXT NOT NULL,
    body TEXT NOT NULL, provider_timestamp TEXT NOT NULL, complete INTEGER NOT NULL,
    baselined INTEGER NOT NULL, observed_at TEXT NOT NULL,
    UNIQUE(source_key, evidence, body)
);
CREATE INDEX IF NOT EXISTS inbox_device ON inbox_records(device_id, seq);
CREATE INDEX IF NOT EXISTS inbox_occurrence ON inbox_records(source_key, evidence);
CREATE TABLE IF NOT EXISTS inbox_outbox (
    record_id TEXT PRIMARY KEY REFERENCES inbox_records(id),
    state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','published','suppressed'))
);
PRAGMA foreign_keys=ON;
"""


class SqliteInboxStore:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._lock = asyncio.Lock()

    @classmethod
    async def open(cls, path: Path) -> "SqliteInboxStore":
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

    async def _one(self, sql: str, parameters: tuple = ()) -> aiosqlite.Row | None:
        async with self._connection.execute(sql, parameters) as cursor:
            return await cursor.fetchone()

    async def ingest(self, snapshot: InboxSnapshot) -> IngestResult:
        async with self._lock:
            try:
                await self._connection.execute("BEGIN IMMEDIATE")
                result = await self._ingest(snapshot)
                await self._connection.commit()
                return result
            except BaseException:
                # aiosqlite queues operations; rollback also follows a cancelled write.
                await asyncio.shield(self._connection.rollback())
                raise

    async def _ingest(self, snapshot: InboxSnapshot) -> IngestResult:
        source = snapshot.source
        started = snapshot.started_at.isoformat()
        previous = await self._one("SELECT * FROM inbox_sources WHERE source_key=?", (source.key,))
        # Different processes are unsupported owners, but stale snapshots must not regress the ledger.
        if previous is not None and snapshot.started_at < datetime.fromisoformat(previous["last_started_at"]):
            return IngestResult(0, 0, False)
        first = (
            await self._one(
                "SELECT 1 FROM inbox_baselines WHERE source_key=? AND subscription_generation=?",
                (source.key, snapshot.subscription_generation),
            )
            is None
        )
        # A replacement/reset storage generation invalidates pending work for its predecessor.
        await self._connection.execute(
            "UPDATE inbox_records SET subscription_uncertain=1 "
            "WHERE device_id=? AND storage=? AND source_key!=?",
            (source.device_id.value, source.storage, source.key),
        )
        await self._connection.execute(
            "UPDATE inbox_records SET subscription_uncertain=(subscription_generation != ?) "
            "WHERE source_key=?",
            (snapshot.subscription_generation, source.key),
        )
        # Pending events from another subscription must not feed an assistant for the new SIM.
        await self._connection.execute(
            "UPDATE inbox_outbox SET state='suppressed' WHERE state='pending' AND record_id IN "
            "(SELECT id FROM inbox_records WHERE device_id=? AND subscription_uncertain=1)",
            (source.device_id.value,),
        )
        queued = 0
        for item in snapshot.items:
            if not item.complete and await self._one(
                "SELECT 1 FROM inbox_records WHERE source_key=? AND evidence=? AND complete=1",
                (source.key, item.occurrence_evidence),
            ):
                continue
            exact = await self._one(
                "SELECT * FROM inbox_records WHERE source_key=? AND evidence=? AND body=?",
                (source.key, item.occurrence_evidence, item.body),
            )
            partial = exact or await self._one(
                "SELECT * FROM inbox_records WHERE source_key=? AND evidence=? "
                "AND complete=0 ORDER BY seq LIMIT 1",
                (source.key, item.occurrence_evidence),
            )
            if partial is not None:
                if partial["complete"]:
                    continue  # Overlapping or older scans cannot make it incomplete again.
                record_id = partial["id"]
                baseline = bool(partial["baselined"]) or first
                await self._connection.execute(
                    "UPDATE inbox_records SET body=?,complete=?,baselined=? WHERE id=?",
                    (item.body, item.complete, baseline, record_id),
                )
                uncertain = bool(partial["subscription_uncertain"])
            else:
                record_id, baseline, uncertain = uuid4().hex, first, False
                await self._connection.execute(
                    "INSERT INTO inbox_records(id,source_key,device_id,storage_generation,storage,"
                    "subscription_generation,evidence,provider_id,sender,sender_kind,body,provider_timestamp,"
                    "complete,baselined,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        record_id,
                        source.key,
                        source.device_id.value,
                        source.storage_generation,
                        source.storage,
                        snapshot.subscription_generation,
                        item.occurrence_evidence,
                        item.provider_id,
                        item.sender.value,
                        item.sender.kind.value,
                        item.body,
                        item.provider_timestamp,
                        item.complete,
                        baseline,
                        snapshot.finished_at.isoformat(),
                    ),
                )
            if item.complete and not baseline and not uncertain:
                async with self._connection.execute(
                    "INSERT OR IGNORE INTO inbox_outbox(record_id) VALUES(?)", (record_id,)
                ) as cursor:
                    queued += cursor.rowcount
        await self._connection.execute(
            "INSERT OR IGNORE INTO inbox_baselines VALUES(?,?)",
            (source.key, snapshot.subscription_generation),
        )
        await self._connection.execute(
            "INSERT INTO inbox_sources VALUES(?,?) ON CONFLICT(source_key) "
            "DO UPDATE SET last_started_at=excluded.last_started_at",
            (source.key, started),
        )
        return IngestResult(len(snapshot.items), queued, first)

    async def pending_events(self, device_id: CellularDeviceId, limit: int = 100) -> tuple[str, ...]:
        if not 1 <= limit <= 200:
            raise ValueError("Event batch requires limit 1–200")
        async with self._lock:
            async with self._connection.execute(
                "SELECT o.record_id FROM inbox_outbox o JOIN inbox_records r ON r.id=o.record_id "
                "WHERE r.device_id=? AND o.state='pending' AND r.subscription_uncertain=0 "
                "ORDER BY r.seq LIMIT ?",
                (device_id.value, limit),
            ) as cursor:
                return tuple(row[0] for row in await cursor.fetchall())

    async def acknowledge_event(self, record_id: str) -> None:
        async with self._lock:
            await self._connection.execute(
                "UPDATE inbox_outbox SET state='published' WHERE state='pending' AND record_id=?",
                (record_id,),
            )

    async def list_records(
        self, device_id: CellularDeviceId, *, limit: int, offset: int
    ) -> tuple[InboxRecord, ...]:
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("Inbox page requires limit 1–200 and a nonnegative offset")
        async with self._lock:
            async with self._connection.execute(
                "SELECT * FROM inbox_records WHERE device_id=? ORDER BY seq DESC LIMIT ? OFFSET ?",
                (device_id.value, limit, offset),
            ) as cursor:
                return tuple(self._record(row) for row in await cursor.fetchall())

    @staticmethod
    def _record(row: aiosqlite.Row) -> InboxRecord:
        return InboxRecord(
            row["id"],
            InboxSource(CellularDeviceId(row["device_id"]), row["storage_generation"], row["storage"]),
            InboxItem(
                row["provider_id"],
                SmsAddress(row["sender"], SmsAddressKind(row["sender_kind"])),
                row["body"],
                row["provider_timestamp"],
                bool(row["complete"]),
            ),
            row["subscription_generation"],
            bool(row["subscription_uncertain"]),
            bool(row["baselined"]),
            datetime.fromisoformat(row["observed_at"]),
        )
