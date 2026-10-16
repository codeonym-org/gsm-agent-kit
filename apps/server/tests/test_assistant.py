"""Offline integration coverage: HTTP device fixtures, real CQRS and SQLite, fake AI."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest
from dishka import Provider, Scope, provide
from gsm_agent.application.commands.process_reply import ProcessNextReply
from gsm_agent.application.events.sms_received import SmsReceived
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.replies import ReplyPolicy, ReplyState
from gsm_agent_core.ai import AgentUnavailableError, AIAgent
from gsm_agent_core.domain.agent import AgentInput, ReplyDecision
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_server.runtime.app import create_app
from gsm_agent_server.runtime.settings import (
    AssistantSettings,
    DeviceSettings,
    InboxSettings,
    SubmissionSettings,
    ZteHttpSettings,
)
from gsm_agent_zte_mf833t import ZteMf833tDevice
from mediary.cqrs import CommandSender, EventPublisher
from pydantic import SecretStr, ValidationError

from .test_devices_api import TestSettings
from .test_inbox_api import message


class FakeAgent:
    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.inputs: list[AgentInput] = []

    async def invoke(self, request: AgentInput) -> ReplyDecision:
        self.inputs.append(request)
        decision = self.decisions.pop(0)
        if isinstance(decision, BaseException):
            raise decision
        return decision

    async def stream(self, request: AgentInput):
        yield await self.invoke(request)


class FakeAIProvider(Provider):
    scope = Scope.APP

    def __init__(self, agent: FakeAgent):
        super().__init__()
        self.agent = agent

    @provide(override=True)
    def ai_agent(self) -> AIAgent:
        return self.agent


def setup(tmp_path, monkeypatch, agent, *, dry_run=False, outcomes=None):
    rows, posts = [], []
    outcomes = outcomes if outcomes is not None else ["3"] * 20
    original = ZteMf833tDevice.__init__

    def respond(request):
        if request.url.path.endswith("config.js"):
            return httpx.Response(200, text="DEVICE: 'datacard/mf833T'")
        if request.method == "POST":
            posts.append(parse_qs(request.content.decode()))
            return httpx.Response(200, json={"result": "success"})
        cmd = request.url.params["cmd"]
        if cmd == "sms_page_data":
            return httpx.Response(200, json={"messages": list(rows)})
        if cmd == "sms_cmd_status_info":
            return httpx.Response(200, json={"sms_cmd_status_result": outcomes.pop(0)})
        return httpx.Response(
            200, json={"network_provider": "Fictional", "network_type": "LTE", "signalbar": "3"}
        )

    def init(self, device_id, settings, **kwargs):
        original(self, device_id, settings, transport=httpx.MockTransport(respond))

    async def idle(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(ZteMf833tDevice, "__init__", init)
    # Drain explicitly for deterministic restart/cancellation assertions; worker tested separately.
    monkeypatch.setattr("gsm_agent_server.runtime.app.poll_inboxes", idle)
    monkeypatch.setattr("gsm_agent_server.runtime.app.process_replies", idle)
    settings = TestSettings(
        device=DeviceSettings(
            id="zte", adapter="zte-mf833t", zte_mf833t=ZteHttpSettings(send_poll_interval_seconds=0.001)
        ),
        inbox=InboxSettings(enabled=True, database_path=tmp_path / "inbox.db"),
        submissions=SubmissionSettings(enabled=not dry_run, database_path=tmp_path / "submissions.db"),
        assistant=AssistantSettings(
            enabled=True, dry_run=dry_run, default_region="MA", database_path=tmp_path / "conversation.db"
        ),
        api_token=SecretStr("fictional-token"),
    )

    @asynccontextmanager
    async def runtime(config=settings):
        app = create_app(config, FakeAIProvider(agent))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app),
                base_url="http://api.invalid",
                headers={"Authorization": "Bearer fictional-token"},
            ) as api:
                async with app.state.dishka_container() as scope:
                    yield api, scope

    return rows, posts, settings, runtime


async def ingest(api):
    result = await api.post("/api/devices/zte/inbox/ingest")
    assert result.status_code == 200
    return result.json()


async def drain(scope):
    commands = await scope.get(CommandSender)
    return await commands.send(ProcessNextReply())


async def test_event_to_reply_normalization_budget_persistent_history_and_dedup(tmp_path, monkeypatch):
    agent = FakeAgent(ReplyDecision("reply", "**Hello** world. " * 25), ReplyDecision("reply", "I remember."))
    rows, posts, settings, runtime = setup(tmp_path, monkeypatch, agent)
    async with runtime() as (api, scope):
        assert (await ingest(api))["baselined"]
        rows.append(message(text="Remember my name: fictional."))
        assert (await ingest(api))["queued"] == 1
        inbox = await scope.get(InboxStore)
        record = (await inbox.list_records(CellularDeviceId("zte"), limit=1, offset=0))[0]
        publisher = await scope.get(EventPublisher)
        await publisher.publish(SmsReceived(record.id))  # Duplicate at-least-once event.
        assert await drain(scope)
        assert not await drain(scope)
        assert len(posts) == 2 and len(agent.inputs) == 1
        sent = [bytes.fromhex(post["MessageBody"][0]).decode("utf-16-be") for post in posts]
        assert all("**" not in text for text in sent)
        assert sum(map(len, sent)) <= settings.submissions.max_total_chars
        assert (await api.get("/api/devices/zte/assistant")).json() == {
            "auto_reply": True,
            "dry_run": False,
            "jobs": {"completed": 1},
        }
        jobs = (await api.get("/api/devices/zte/assistant/jobs")).json()
        assert jobs[0]["state"] == "completed" and jobs[0]["record_id"] == record.id
        assert set(jobs[0]) == {"record_id", "request_id", "state", "issue", "created_at"}
        progress = await api.get(f"/api/devices/zte/submissions/{jobs[0]['request_id']}")
        assert progress.json()["complete"]
        assert (await api.get("/api/devices/zte/assistant/jobs?limit=0")).status_code == 422
        assert (await api.get("/api/devices/missing/assistant")).status_code == 404
        assert (
            await api.get("/api/devices/zte/assistant", headers={"Authorization": "bad"})
        ).status_code == 401
    async with runtime() as (api, scope):
        assert not await drain(scope) and len(posts) == 2
        rows.append(message("2", text="What is my name?"))
        await ingest(api)
        assert await drain(scope)
        history = agent.inputs[1].messages
        assert [msg.role for msg in history] == ["user", "assistant", "user"]
        assert history[1].content == "\n".join(sent)
        assert agent.inputs[0].thread_id == agent.inputs[1].thread_id
        assert "+212" not in agent.inputs[0].thread_id


async def test_ignore_provider_failure_dry_run_and_disabled_status(tmp_path, monkeypatch, caplog):
    agent = FakeAgent(
        ReplyDecision("ignore", ignore_reason="spam"),
        AgentUnavailableError("private provider data"),
        ReplyDecision("reply", "**Preview**"),
    )
    rows, posts, settings, runtime = setup(tmp_path, monkeypatch, agent, dry_run=True)
    async with runtime() as (api, scope):
        await ingest(api)
        for slot in ("1", "2", "3"):
            rows.append(message(slot))
            await ingest(api)
            assert await drain(scope)
        assert posts == []
        assert (await api.get("/api/devices/zte/assistant")).json() == {
            "auto_reply": True,
            "dry_run": True,
            "jobs": {"ignored": 1, "failed": 1, "dry_run": 1},
        }
        assert "private provider data" not in caplog.text
    async with runtime() as (api, scope):
        assert not await drain(scope) and len(agent.inputs) == 3
    disabled = create_app(TestSettings())
    async with disabled.router.lifespan_context(disabled):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(disabled), base_url="http://api.invalid"
        ) as api:
            assert (await api.get("/api/devices/demo-device/assistant")).json() == {
                "auto_reply": False,
                "dry_run": True,
                "jobs": {},
            }


async def test_partial_unknown_submission_records_only_accepted_text_and_never_resends(tmp_path, monkeypatch):
    agent = FakeAgent(ReplyDecision("reply", "A longer response. " * 20))
    rows, posts, _, runtime = setup(tmp_path, monkeypatch, agent, outcomes=["3", "invalid"])
    async with runtime() as (api, scope):
        await ingest(api)
        rows.append(message())
        await ingest(api)
        store = await scope.get(ReplyStore)
        job = await store.next_job()
        assert job is not None
        assert await drain(scope)
        assert len(posts) == 2
        history = await store.history(job.conversation_key, ReplyPolicy())
        assert len(history) == 2
        accepted = bytes.fromhex(posts[0]["MessageBody"][0]).decode("utf-16-be")
        assert history[1].content == accepted
    async with runtime() as (api, scope):
        assert not await drain(scope) and len(posts) == 2


async def test_crash_after_submission_reconciles_without_model_or_device_replay(tmp_path, monkeypatch):
    agent = FakeAgent(ReplyDecision("reply", "Fictional answer"))
    rows, posts, _, runtime = setup(tmp_path, monkeypatch, agent)
    async with runtime() as (api, scope):
        await ingest(api)
        rows.append(message())
        await ingest(api)
        store = await scope.get(ReplyStore)
        job = await store.next_job()
        assert job is not None
        original_finish = store.finish

        async def cancelled(*args, **kwargs):
            raise asyncio.CancelledError

        monkeypatch.setattr(store, "finish", cancelled)
        with pytest.raises(asyncio.CancelledError):
            await drain(scope)
        assert len(posts) == 1
        monkeypatch.setattr(store, "finish", original_finish)
    async with runtime() as (api, scope):
        assert await drain(scope)
        assert not await drain(scope)
        assert len(posts) == 1 and len(agent.inputs) == 1
        store = await scope.get(ReplyStore)
        assert len(await store.history(job.conversation_key, ReplyPolicy())) == 2


async def test_sim_change_during_generation_suppresses_send(tmp_path, monkeypatch):
    agent = FakeAgent(ReplyDecision("reply", "Must not send"))
    rows, posts, _, runtime = setup(tmp_path, monkeypatch, agent)
    async with runtime() as (api, scope):
        await ingest(api)
        rows.append(message())
        await ingest(api)
        store = await scope.get(InboxStore)
        original = store.get
        calls = 0

        async def changed(record_id):
            nonlocal calls
            calls += 1
            record = await original(record_id)
            return replace(record, subscription_uncertain=True) if calls > 1 and record else record

        monkeypatch.setattr(store, "get", changed)
        assert await drain(scope) and posts == []
        assert (await api.get("/api/devices/zte/assistant")).json()["jobs"] == {"ignored": 1}


def test_auto_reply_requires_inbox_and_live_sending_requires_submission():
    with pytest.raises(ValidationError, match="inbox"):
        TestSettings(assistant=AssistantSettings(enabled=True))
    with pytest.raises(ValidationError, match="submission"):
        TestSettings(
            inbox=InboxSettings(enabled=True), assistant=AssistantSettings(enabled=True, dry_run=False)
        )


async def test_prepared_reply_survives_restart_without_second_model_call(tmp_path, monkeypatch):
    agent = FakeAgent()
    rows, posts, _, runtime = setup(tmp_path, monkeypatch, agent)
    async with runtime() as (api, scope):
        await ingest(api)
        rows.append(message())
        await ingest(api)
        store = await scope.get(ReplyStore)
        job = await store.next_job()
        assert job is not None
        await store.update(job.record_id, ReplyState.PREPARED, text="Saved decision")
    async with runtime() as (api, scope):
        assert await drain(scope) and not await drain(scope)
        assert len(posts) == 1 and agent.inputs == []


async def test_interrupted_before_submission_commit_never_sends_on_recovery(tmp_path, monkeypatch):
    agent = FakeAgent()
    rows, posts, _, runtime = setup(tmp_path, monkeypatch, agent)
    async with runtime() as (api, scope):
        await ingest(api)
        rows.append(message())
        await ingest(api)
        store = await scope.get(ReplyStore)
        job = await store.next_job()
        assert job is not None
        await store.update(job.record_id, ReplyState.SUBMITTING, text="Uncertain intent")
    async with runtime() as (api, scope):
        assert await drain(scope) and not await drain(scope)
        jobs = (await api.get("/api/devices/zte/assistant/jobs")).json()
        assert jobs[0]["state"] == "interrupted" and jobs[0]["issue"] == "no_submission_evidence"
        assert posts == [] and agent.inputs == []


async def test_generation_cancellation_stays_terminal_on_restart(tmp_path, monkeypatch):
    agent = FakeAgent()
    entered = asyncio.Event()

    async def wait(request):
        entered.set()
        await asyncio.Event().wait()
        return ReplyDecision("reply", "Unreachable")

    monkeypatch.setattr(agent, "invoke", wait)
    rows, posts, _, runtime = setup(tmp_path, monkeypatch, agent)
    async with runtime() as (api, scope):
        await ingest(api)
        rows.append(message())
        await ingest(api)
        task = asyncio.create_task(drain(scope))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await api.get("/api/devices/zte/assistant")).json()["jobs"] == {"failed": 1}
    async with runtime() as (api, scope):
        assert not await drain(scope) and posts == []


async def test_background_polling_and_worker_process_new_inbound(tmp_path, monkeypatch):
    from gsm_agent_server.runtime.inbox import poll_inboxes
    from gsm_agent_server.runtime.replies import process_replies

    agent = FakeAgent(ReplyDecision("reply", "Background answer"))
    rows, posts, settings, runtime = setup(tmp_path, monkeypatch, agent)
    monkeypatch.setattr("gsm_agent_server.runtime.app.poll_inboxes", poll_inboxes)
    monkeypatch.setattr("gsm_agent_server.runtime.app.process_replies", process_replies)
    config = settings.model_copy(
        update={
            "inbox": settings.inbox.model_copy(update={"poll_interval_seconds": 0.01}),
            "assistant": settings.assistant.model_copy(update={"poll_interval_seconds": 0.01}),
        }
    )
    async with runtime(config) as (api, scope):
        store = await scope.get(InboxStore)
        # Wait until the first successful empty scan established a baseline.
        async with asyncio.timeout(3):
            while (await ingest(api))["baselined"]:
                await asyncio.sleep(0.01)
        rows.append(message())
        async with asyncio.timeout(3):
            while (await api.get("/api/devices/zte/assistant")).json()["jobs"] != {"completed": 1}:
                await asyncio.sleep(0.01)
        assert len(posts) == 1 and len(agent.inputs) == 1
        assert len(await store.list_records(CellularDeviceId("zte"), limit=1, offset=0)) == 1
