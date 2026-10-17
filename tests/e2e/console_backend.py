"""Browser-test runtime: real CQRS/SQLite, synthetic device and AI, no external I/O.

Fixture controls exist only in this test process and are never mounted by the
production application. Bind to loopback and use a temporary state directory.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from dishka import Provider, Scope, provide
from fastapi import HTTPException
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent_core.ai import AIAgent
from gsm_agent_core.capabilities.catalog import (
    DEVICE_STATUS_READ,
    SMS_INBOX_READ,
    SMS_SEND,
    CapabilityBinding,
    CapabilitySet,
)
from gsm_agent_core.domain.agent import AgentInput, ReplyDecision
from gsm_agent_core.domain.devices import Availability, CellularDeviceId, DeviceStatus
from gsm_agent_core.domain.sms import InboxItem, InboxSnapshot, InboxSource, SmsAddress
from gsm_agent_core.domain.submission import (
    PreparedSms,
    SmsSendConstraints,
    SmsSubmissionResult,
    SubmissionOutcome,
    SubmissionReason,
)
from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import (
    AssistantSettings,
    BalanceSettings,
    InboxSettings,
    Settings,
    SubmissionSettings,
)
from gsm_agent_simulated import SimulatedDevice
from pydantic import BaseModel, SecretStr
from pydantic_settings import SettingsConfigDict


class ConsoleDevice(SimulatedDevice):
    def __init__(self) -> None:
        super().__init__(CellularDeviceId("demo-sms"))
        self._capabilities = CapabilitySet(
            CapabilityBinding(DEVICE_STATUS_READ, self),
            CapabilityBinding(SMS_INBOX_READ, self),
            CapabilityBinding(SMS_SEND, self),
        )
        self._manifest = replace(
            self.manifest,
            adapter_id="simulated-sms-test",
            model=replace(self.manifest.model, name="Simulated SMS device"),
            capabilities=self._capabilities.supported,
        )
        self.items: list[InboxItem] = []
        self.submissions: list[PreparedSms] = []
        self.outcome = SubmissionOutcome.ACCEPTED
        self.gate = asyncio.Event()
        self.gate.set()

    @property
    def constraints(self) -> SmsSendConstraints:
        return SmsSendConstraints()

    async def scan(self) -> InboxSnapshot:
        now = datetime.now(UTC)
        return InboxSnapshot(
            InboxSource(self.device_id, "fixture", "memory"), "fixture", now, now, tuple(self.items)
        )

    async def read(self) -> DeviceStatus:
        return DeviceStatus(self._availability, datetime.now(UTC), "Simulated carrier", "LTE", 80)

    async def submit(self, sms: PreparedSms) -> SmsSubmissionResult:
        self.submissions.append(sms)
        await self.gate.wait()
        return SmsSubmissionResult(
            sms.message_id,
            sms.attempt_id,
            self.outcome,
            SubmissionReason.INVALID_RESPONSE if self.outcome is SubmissionOutcome.UNKNOWN else None,
        )


class FixtureAgent:
    async def invoke(self, request: AgentInput) -> ReplyDecision:
        await asyncio.sleep(0.05)
        return ReplyDecision("reply", "**Hello!** This is a simulated assistant reply.")

    async def stream(self, request: AgentInput):
        yield await self.invoke(request)


class FixtureProvider(Provider):
    scope = Scope.APP

    def __init__(self, device: ConsoleDevice) -> None:
        super().__init__()
        self.device = device

    @provide(override=True)
    async def devices(self) -> AsyncIterator[DeviceDirectory]:
        status_only = SimulatedDevice(CellularDeviceId("status-only"))
        balance_only = SimulatedDevice(CellularDeviceId("balance-demo"), balance_enabled=True)
        balance_only._manifest = replace(balance_only.manifest, adapter_id="simulated-balance-test")
        try:
            yield ConfiguredDevices(
                (self.device, status_only, balance_only),
                (self.device.manifest, status_only.manifest, balance_only.manifest),
            )
        finally:
            await self.device.close()
            await status_only.close()
            await balance_only.close()

    @provide(override=True)
    def ai_agent(self) -> AIAgent:
        return FixtureAgent()


class FixtureSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, env_prefix="GSM_CONSOLE_FIXTURE_")


class Incoming(BaseModel):
    text: str = "Hello from the simulated SIM."


class Mode(BaseModel):
    outcome: SubmissionOutcome = SubmissionOutcome.ACCEPTED
    hold: bool = False
    availability: Availability = Availability.READY


def build_fixture(path: Path):
    device = ConsoleDevice()
    settings = FixtureSettings(
        balance=BalanceSettings(carrier="simulated"),
        inbox=InboxSettings(enabled=True, database_path=path / "inbox.db", poll_interval_seconds=0.1),
        submissions=SubmissionSettings(enabled=True, database_path=path / "submissions.db"),
        assistant=AssistantSettings(
            enabled=True,
            dry_run=os.environ.get("GSM_CONSOLE_DRY_RUN") == "1",
            database_path=path / "replies.db",
            poll_interval_seconds=0.1,
        ),
        api_token=SecretStr("fixture-api-token"),
    )
    app = create_app(settings, FixtureProvider(device))

    @app.post("/__fixture__/incoming")
    async def incoming(body: Incoming):
        number = str(len(device.items) + 1)
        device.items.append(
            InboxItem(
                number,
                SmsAddress.from_sender("+212600000000"),
                body.text,
                f"fixture-{number}",
                True,
            )
        )
        return {"count": len(device.items)}

    @app.post("/__fixture__/mode")
    async def mode(body: Mode):
        device.outcome = body.outcome
        device._availability = body.availability
        device.gate.clear() if body.hold else device.gate.set()
        return {"ok": True}

    @app.get("/__fixture__/effects")
    async def effects():
        return {"submissions": len(device.submissions)}

    @app.get("/__fixture__/ready")
    async def ready():
        # Wait until the empty inbox has a committed baseline before injecting SMS.
        from gsm_agent.application.ports.inbox import InboxStore

        store = await app.state.dishka_container.get(InboxStore)
        if not await store.list_records(device.device_id, limit=1, offset=0):
            async with app.state.dishka_container() as scope:
                from gsm_agent.application.commands.ingest_inbox import IngestInbox
                from mediary.cqrs import CommandSender

                commands = await scope.get(CommandSender)
                await commands.send(IngestInbox(device.device_id))
        if device.closed:
            raise HTTPException(503)
        return {"ready": True}

    return app


if __name__ == "__main__":
    with TemporaryDirectory(prefix="gsm-console-") as directory:
        uvicorn.run(build_fixture(Path(directory)), host="127.0.0.1", port=8765, log_level="warning")
