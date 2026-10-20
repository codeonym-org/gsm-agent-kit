import asyncio
import errno
import os
import queue
import subprocess
import sys
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from dishka import Provider, Scope, provide
from filelock import SoftFileLock
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.submissions import SubmissionStore
from gsm_agent.application.submissions import PartState
from gsm_agent.application.text import SmsLimits, prepare_sms
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.domain.submission import SmsDestination, SmsSendConstraints
from gsm_agent_server.infra import state_ownership
from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.infra.state_ownership import StateAlreadyOwnedError, StateOwnershipError, own_state
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import (
    AssistantSettings,
    DeviceSettings,
    InboxSettings,
    Settings,
    SubmissionSettings,
)
from gsm_agent_simulated import SimulatedDevice
from pydantic_settings import SettingsConfigDict


class FixtureSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="UNUSED_STATE_FIXTURE_")


def config(path: Path, device_id: str = "synthetic-owner") -> Settings:
    return FixtureSettings(
        device=DeviceSettings(id=device_id),
        submissions=SubmissionSettings(enabled=True, database_path=path),
    )


class TrackedDevices(Provider):
    scope = Scope.APP

    def __init__(self, events: list[str], closing: asyncio.Event | None = None) -> None:
        super().__init__()
        self.events = events
        self.closing = closing
        self.close_started = asyncio.Event()

    @provide(override=True)
    async def devices(self) -> AsyncIterator[DeviceDirectory]:
        self.events.append("device-opened")
        device = SimulatedDevice(CellularDeviceId("synthetic-owner"))
        try:
            yield ConfiguredDevices((device,), (device.manifest,))
        finally:
            self.events.append("device-closing")
            self.close_started.set()
            if self.closing is not None:
                await self.closing.wait()
            await device.close()
            self.events.append("device-closed")


def test_partial_acquisition_failure_releases_other_ledgers(tmp_path):
    first, second = tmp_path / "a.db", tmp_path / "b.db"
    with own_state([second]):
        with pytest.raises(StateAlreadyOwnedError):
            with own_state([second, first]):
                pytest.fail("A competing owner must not enter")
        with own_state([first]):
            pass
    with own_state([first, second]):
        pass
    assert not first.exists() and not second.exists()


def test_duplicate_relative_paths_and_existing_lock_files_are_safe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "state.db"
    with own_state([Path("state.db"), path, tmp_path / "other" / ".." / "state.db"]):
        with pytest.raises(StateAlreadyOwnedError):
            with own_state([path]):
                pass
    assert path.with_name("state.db.owner.lock").exists()
    with own_state([path]):
        pass  # A leftover marker is not a stale lock requiring deletion.


def test_symbolic_link_aliases_share_one_owner(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires additional privileges on this platform")
    with own_state([real / "state.db", alias / "state.db"]):
        with pytest.raises(StateAlreadyOwnedError):
            with own_state([alias / "state.db"]):
                pass


def test_disabled_state_creates_no_files_and_unsupported_native_locks_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(state_ownership, "FileLock", SoftFileLock)
    with own_state([]):
        pass
    assert not list(tmp_path.iterdir())
    with pytest.raises(StateOwnershipError, match="Native filesystem locking"):
        with own_state([tmp_path / "state.db"]):
            pass
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name != "posix", reason="Tests Unix filesystem ENOSYS handling")
def test_filesystem_without_native_locking_does_not_fall_back_to_markers(tmp_path, monkeypatch):
    import filelock._unix

    def unsupported(fd):
        raise OSError(errno.ENOSYS, "synthetic-unsupported-filesystem")

    monkeypatch.setattr(filelock._unix, "_lock_fd_nonblocking", unsupported)
    with pytest.raises(StateOwnershipError, match="native filesystem locking") as error:
        with own_state([tmp_path / "state.db"]):
            pass
    assert "synthetic-unsupported" not in str(error.value)
    assert not (tmp_path / "state.db").exists()


def test_unwritable_state_location_reports_a_sanitized_error(tmp_path):
    parent = tmp_path / "synthetic-private-path"
    parent.write_text("A regular file cannot contain a state database")
    with pytest.raises(StateOwnershipError, match="permissions") as error:
        with own_state([parent / "state.db"]):
            pass
    assert str(parent) not in str(error.value)


def test_independent_process_cannot_acquire_live_state(tmp_path):
    path = tmp_path / "state.db"
    code = """
from pathlib import Path
import sys
from gsm_agent_server.infra.state_ownership import StateAlreadyOwnedError, own_state
try:
    with own_state([Path(sys.argv[1])]):
        raise AssertionError('Unexpected competing state owner')
except StateAlreadyOwnedError:
    print('refused')
"""
    with own_state([path]):
        result = subprocess.run(
            [sys.executable, "-c", code, str(path)], capture_output=True, text=True, timeout=10, check=False
        )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "refused"


@pytest.mark.parametrize("forced", [False, True])
def test_process_exit_releases_native_lock_without_deleting_marker(tmp_path, forced):
    path = tmp_path / "state.db"
    code = """
from pathlib import Path
import sys
from gsm_agent_server.infra.state_ownership import own_state
with own_state([Path(sys.argv[1])]):
    print('owned', flush=True)
    sys.stdin.readline()
"""
    child = subprocess.Popen(
        [sys.executable, "-u", "-c", code, str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ready: queue.Queue[str] = queue.Queue()
    stdout = child.stdout
    assert stdout is not None
    reader = threading.Thread(target=lambda: ready.put(stdout.readline()), daemon=True)
    reader.start()
    try:
        assert ready.get(timeout=10).strip() == "owned"
        with pytest.raises(StateAlreadyOwnedError):
            with own_state([path]):
                pass
        if forced:
            child.kill()
            child.communicate(timeout=10)
        else:
            child.communicate(input="release\n", timeout=10)
            assert child.returncode == 0
        assert path.with_name("state.db.owner.lock").exists()
        with own_state([path]):
            pass
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
        reader.join(timeout=10)


async def test_second_backend_cannot_open_devices_or_recover_an_active_attempt(tmp_path):
    path = tmp_path / "submissions.db"
    events: list[str] = []
    first = create_app(config(path), TrackedDevices(events))
    contender_events: list[str] = []
    # Sharing state is forbidden even when the second logical ID is different.
    second = create_app(config(path, "other-logical-id"), TrackedDevices(contender_events))
    device, request = CellularDeviceId("synthetic-owner"), uuid4()
    async with first.router.lifespan_context(first):
        store = await first.state.dishka_container.get(SubmissionStore)
        await store.create(
            device,
            request,
            SmsDestination("+212600000000"),
            "synthetic-digest",
            prepare_sms("Synthetic SMS", SmsLimits(), SmsSendConstraints()),
        )
        await store.begin_attempt(device, request, 0)
        with pytest.raises(StateAlreadyOwnedError):
            async with second.router.lifespan_context(second):
                pytest.fail("A competing backend must not start")
        record = await store.get(device, request)
        assert record is not None and record.parts[0].state is PartState.IN_PROGRESS
        assert record.parts[0].attempts[0].outcome is None
        assert contender_events == [] and events == ["device-opened"]
    assert events[-1] == "device-closed"
    restarted = create_app(config(path))
    async with restarted.router.lifespan_context(restarted):
        recovered = await restarted.state.dishka_container.get(SubmissionStore)
        record = await recovered.get(device, request)
        assert record is not None and record.parts[0].state is PartState.UNKNOWN
        assert len(record.parts[0].attempts) == 1


async def test_failed_backend_startup_closes_device_and_releases_state(tmp_path):
    path = tmp_path / "directory-not-a-database"
    path.mkdir()
    events: list[str] = []
    app = create_app(config(path), TrackedDevices(events))
    with pytest.raises(Exception, match="unable to open database"):
        async with app.router.lifespan_context(app):
            pass
    assert events == ["device-opened", "device-closing", "device-closed"]
    with own_state([path]):
        pass


async def test_shutdown_retains_ownership_through_cancelled_device_cleanup(tmp_path):
    path = tmp_path / "submissions.db"
    release = asyncio.Event()
    provider = TrackedDevices([], release)
    app = create_app(config(path), provider)
    lifespan = app.router.lifespan_context(app)
    await lifespan.__aenter__()
    shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
    try:
        await asyncio.wait_for(provider.close_started.wait(), timeout=5)
        shutdown.cancel()
        # Repeated cancellation must not cancel resource cleanup or release locks.
        await asyncio.sleep(0)
        shutdown.cancel()
        await asyncio.sleep(0)
        with pytest.raises(StateAlreadyOwnedError):
            with own_state([path]):
                pass
        assert not shutdown.done() and provider.events[-1] == "device-closing"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(shutdown, timeout=5)
    assert provider.events[-1] == "device-closed"
    with own_state([path]):
        pass


async def test_status_only_backend_does_not_create_state_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(FixtureSettings())
    async with app.router.lifespan_context(app):
        assert not list(tmp_path.iterdir())
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("ledger", ["inbox", "submissions", "conversations"])
async def test_each_enabled_ledger_is_reserved_before_composition(tmp_path, ledger):
    config = FixtureSettings(
        inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db"),
        submissions=SubmissionSettings(enabled=True, database_path=tmp_path / "submissions.db"),
        assistant=AssistantSettings(enabled=True, database_path=tmp_path / "conversations.db"),
    )
    events: list[str] = []
    app = create_app(config, TrackedDevices(events))
    with own_state([tmp_path / f"{ledger}.db"]):
        with pytest.raises(StateAlreadyOwnedError):
            async with app.router.lifespan_context(app):
                pass
    assert events == []
    with own_state([tmp_path / name for name in ("inbox.db", "submissions.db", "conversations.db")]):
        pass


async def test_backends_with_independent_state_can_run_together(tmp_path):
    first = create_app(config(tmp_path / "first" / "submissions.db"))
    second = create_app(config(tmp_path / "second" / "submissions.db"))
    async with first.router.lifespan_context(first):
        async with second.router.lifespan_context(second):
            assert await first.state.dishka_container.get(SubmissionStore)
            assert await second.state.dishka_container.get(SubmissionStore)
