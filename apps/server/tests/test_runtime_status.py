"""Recorded runtime status through real CQRS/DI with synthetic worker failures."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from gsm_agent.application.commands.process_reply import ProcessNextReply
from gsm_agent.application.queries.runtime import GetRuntimeStatus
from gsm_agent.application.runtime import RuntimeStatus, WorkerId, WorkerState, WorkerStatus
from gsm_agent_core.capabilities.catalog import SMS_INBOX_READ, CapabilityKey
from gsm_agent_core.domain.devices import AdapterManifest, CellularDeviceId, DeviceModel, DeviceReadIssue
from gsm_agent_core.domain.sms import InboxReadError, InboxSnapshot, InboxSource
from gsm_agent_server.infra.runtime import RuntimeMonitor
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.replies import process_replies
from gsm_agent_server.runtime.settings import AssistantSettings, InboxSettings, Settings
from gsm_agent_server.runtime.workers import observe_worker
from mediary.cqrs import Command, CommandSender, Query
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from .test_devices_api import TestDevicesProvider

PRIVATE_ERROR = "synthetic-private-token +212600000000 SMS body http://private.invalid /private/state.db"


class FixtureSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="UNUSED_RUNTIME_FIXTURE_")


class InboxDevice:
    manifest = AdapterManifest("fixture", "0.1.0", DeviceModel("Fixture", "Inbox"), (SMS_INBOX_READ.id,))

    def __init__(self, name: str, error: Exception | None = None, *, blocked: bool = False):
        self.device_id = CellularDeviceId(name)
        self.error = error
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.blocked = blocked
        self.scans = 0
        self.closed = False

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        return cast(P, self) if key is SMS_INBOX_READ else None

    async def describe(self):
        raise AssertionError("Runtime query must not inspect devices")

    async def scan(self) -> InboxSnapshot:
        self.scans += 1
        self.entered.set()
        if self.blocked:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
        if self.error is not None:
            raise self.error
        now = datetime.now(UTC)
        return InboxSnapshot(InboxSource(self.device_id, "fixture", "memory"), "fixture", now, now, ())

    async def close(self):
        self.closed = True


async def wait_for_worker(
    monitor: RuntimeMonitor, worker: WorkerId, predicate: Callable[[WorkerStatus], bool]
):
    async with asyncio.timeout(3):
        while True:
            status = next(row for row in (await monitor.read()).workers if row.worker_id is worker)
            if predicate(status):
                return status
            await asyncio.sleep(0.001)


def test_runtime_is_a_query_and_not_a_command():
    assert issubclass(GetRuntimeStatus, Query)
    assert not issubclass(GetRuntimeStatus, Command)


async def test_runtime_query_is_authenticated_uncached_and_does_not_probe_devices_or_stores(tmp_path):
    device = InboxDevice("never-probed")
    settings = FixtureSettings(api_token=SecretStr("synthetic-token"))
    settings.inbox.database_path = tmp_path / "not-opened" / "inbox.db"
    app = create_app(settings, TestDevicesProvider(device))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            assert (await api.get("/api/runtime")).status_code == 401
            for _ in range(2):
                response = await api.get("/api/runtime", headers={"Authorization": "Bearer synthetic-token"})
                assert response.status_code == 200
                assert response.headers["Cache-Control"] == "no-store"
                payload = response.json()
                assert [worker["state"] for worker in payload["workers"]] == ["disabled", "disabled"]
                assert all(worker["iterations_started"] == 0 for worker in payload["workers"])
                assert "synthetic-token" not in response.text
                assert datetime.fromisoformat(payload["observed_at"]).utcoffset() is not None
                assert datetime.fromisoformat(payload["started_at"]).utcoffset() is not None
            assert (await api.get("/health")).json()["status"] == "ok"
            assert device.scans == 0 and not (tmp_path / "not-opened").exists()
    assert device.closed


@pytest.mark.parametrize(
    "error,issue",
    [(InboxReadError(DeviceReadIssue.OFFLINE), "offline"), (RuntimeError(PRIVATE_ERROR), "operation_failed")],
)
async def test_inbox_sweep_failure_survives_successful_device_then_recovers(tmp_path, caplog, error, issue):
    failing, healthy = InboxDevice("failing", error), InboxDevice("healthy")
    settings = FixtureSettings(
        inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db", poll_interval_seconds=0.01),
    )
    app = create_app(settings, TestDevicesProvider(failing, healthy))
    async with app.router.lifespan_context(app):
        monitor = await app.state.dishka_container.get(RuntimeMonitor)
        degraded = await wait_for_worker(
            monitor, WorkerId.INBOX, lambda row: row.state is WorkerState.DEGRADED
        )
        assert healthy.scans >= 1
        assert degraded.iterations_failed >= 1 and degraded.consecutive_failures >= 1
        assert degraded.last_issue == issue
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            response = await api.get("/api/runtime")
            assert response.status_code == 200 and PRIVATE_ERROR not in response.text
            assert (await api.get("/health")).json()["status"] == "ok"
        failing.error = None
        recovered = await wait_for_worker(
            monitor,
            WorkerId.INBOX,
            lambda row: row.state is WorkerState.WAITING and row.iterations_succeeded >= 1,
        )
        assert recovered.consecutive_failures == 0
        assert recovered.iterations_failed >= degraded.iterations_failed
        assert (
            recovered.last_failure_at is not None
            and recovered.last_success_at is not None
            and recovered.last_success_at >= recovered.last_failure_at
        )
        # Snapshots and historical issue/time remain stable after recovery.
        assert degraded.state is WorkerState.DEGRADED and recovered.last_issue == issue
    assert PRIVATE_ERROR not in caplog.text
    stopped = (await monitor.read()).workers[0]
    assert stopped.state is WorkerState.STOPPED


async def test_cancellation_stops_running_inbox_without_counting_failure_or_querying_device(tmp_path):
    device = InboxDevice("blocked", blocked=True)
    app = create_app(
        FixtureSettings(inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db")),
        TestDevicesProvider(device),
    )
    async with app.router.lifespan_context(app):
        monitor = await app.state.dishka_container.get(RuntimeMonitor)
        await asyncio.wait_for(device.entered.wait(), 3)
        before = device.scans
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://api.invalid"
        ) as api:
            for _ in range(3):
                payload = (await api.get("/api/runtime")).json()
                assert payload["workers"][0]["state"] == "running"
        assert device.scans == before
    assert device.cancelled.is_set() and device.closed
    stopped = (await monitor.read()).workers[0]
    assert stopped.state is WorkerState.STOPPED
    assert stopped.iterations_started == 1 and stopped.iterations_failed == 0
    assert stopped.last_issue is None


@pytest.mark.parametrize("failure", [False, True])
async def test_unexpected_worker_return_or_exception_is_recorded_without_exception_payload(failure, caplog):
    monitor = RuntimeMonitor(inbox_enabled=True, replies_enabled=False)

    async def unexpected():
        if failure:
            raise RuntimeError(PRIVATE_ERROR)

    await observe_worker(unexpected, monitor, WorkerId.INBOX)
    status = (await monitor.read()).workers[0]
    assert status.state is WorkerState.FAILED and status.last_issue == "unexpected_exit"
    assert status.last_failure_at is not None and status.iterations_failed == 0
    assert PRIVATE_ERROR not in caplog.text


async def test_enabled_worker_starts_as_starting_and_clean_shutdown_marks_stopped(
    tmp_path,
):
    monitor = RuntimeMonitor(inbox_enabled=True, replies_enabled=False)
    assert [row.state for row in (await monitor.read()).workers] == [
        WorkerState.STARTING,
        WorkerState.DISABLED,
    ]
    called = False

    async def operation():
        nonlocal called
        called = True

    task = asyncio.create_task(observe_worker(operation, monitor, WorkerId.INBOX))
    task.cancel()  # No operation coroutine should be created before the first step.
    await asyncio.gather(task, return_exceptions=True)
    assert not called
    app = create_app(FixtureSettings(inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db")))
    async with app.router.lifespan_context(app):
        actual = await app.state.dishka_container.get(RuntimeMonitor)
        # Exit immediately. Lifecycle cleanup must still record stopped.
    assert (await actual.read()).workers[0].state is WorkerState.STOPPED


class ReplyCommands:
    def __init__(self):
        self.error: Exception | None = RuntimeError(PRIVATE_ERROR)
        self.blocked = False
        self.entered = asyncio.Event()
        self.calls = 0

    async def send(self, command, *args, **kwargs):
        assert isinstance(command, ProcessNextReply)
        self.calls += 1
        if self.blocked:
            self.entered.set()
            await asyncio.Event().wait()
        if self.error:
            raise self.error
        return False  # An idle queue is a successful iteration, not an SMS outcome.


class ReplyWorkerProvider(Provider):
    scope = Scope.APP

    def __init__(self, monitor, commands):
        super().__init__()
        self.monitor, self.commands = monitor, commands

    @provide
    def runtime_monitor(self) -> RuntimeMonitor:
        return self.monitor

    @provide
    def command_sender(self) -> CommandSender:
        return self.commands


async def test_reply_worker_failure_recovery_and_cancellation_are_recorded_without_ai_or_sends(caplog):
    monitor = RuntimeMonitor(inbox_enabled=False, replies_enabled=True)
    commands = ReplyCommands()
    container = make_async_container(ReplyWorkerProvider(monitor, commands))
    task = asyncio.create_task(
        observe_worker(
            lambda: process_replies(container, AssistantSettings(enabled=True, poll_interval_seconds=0.01)),
            monitor,
            WorkerId.REPLIES,
        )
    )
    try:
        degraded = await wait_for_worker(
            monitor, WorkerId.REPLIES, lambda row: row.state is WorkerState.DEGRADED
        )
        assert degraded.last_issue == "operation_failed"
        commands.error = None
        recovered = await wait_for_worker(
            monitor,
            WorkerId.REPLIES,
            lambda row: row.state is WorkerState.WAITING and row.iterations_succeeded >= 1,
        )
        assert recovered.consecutive_failures == 0 and recovered.iterations_failed >= 1
        commands.blocked = True
        await asyncio.wait_for(commands.entered.wait(), 3)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await container.close()
    assert (await monitor.read()).workers[1].state is WorkerState.STOPPED
    assert PRIVATE_ERROR not in caplog.text


@pytest.mark.parametrize(
    "error,expected",
    [(TimeoutError(PRIVATE_ERROR), "timeout"), (ValueError(PRIVATE_ERROR), "operation_failed")],
)
async def test_issue_classification_never_retains_exception_text(error, expected):
    from gsm_agent_server.infra.runtime import worker_issue

    monitor = RuntimeMonitor(inbox_enabled=True, replies_enabled=False)
    monitor.begin(WorkerId.INBOX)
    monitor.failed(WorkerId.INBOX, worker_issue(error))
    status: RuntimeStatus = await monitor.read()
    assert status.workers[0].last_issue == expected
    assert PRIVATE_ERROR not in repr(status)
