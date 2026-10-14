import pytest
from dishka import Provider, Scope
from mediary.cqrs import CommandSender

from gsm_agent.application.commands.poll_inbox import PollInbox
from gsm_agent.application.ports.ai_agent import AIAgent
from gsm_agent.application.ports.conversations import ConversationStore
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.modem import ModemPort
from gsm_agent.di.container import build_container
from gsm_agent.domain.agent import AgentStreamEvent, ChatMessage, ReplyDecision
from gsm_agent.domain.balance import BalanceResult
from gsm_agent.domain.errors import SmsSendUncertainError
from gsm_agent.domain.sms import MessageState, ModemStatus, SmsMessage
from gsm_agent.domain.sms_text import MemoryLimits, delivered_text
from gsm_agent.runtime.config import ListenerConfig, StorageConfig
from gsm_agent.runtime.settings import Settings


class FakeModem:
    def __init__(self):
        self.messages = []
        self.sends = []
        self.uncertain = False
        self.uncertain_at = None
        self.balance_codes = []

    async def consult_balance(self, code):
        self.balance_codes.append(code.value)
        return BalanceResult(code.value, "Votre solde: 12,50 DH", "2026-10-13T12:00:00+00:00")

    async def get_status(self):
        return ModemStatus("inwi", "LTE", 5, 0)

    async def list_messages(self):
        return self.messages

    async def send_sms(self, recipient, message):
        self.sends.append((recipient.value, message))
        if self.uncertain or len(self.sends) == self.uncertain_at:
            raise SmsSendUncertainError("unknown")


class FakeAgent:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.ignore = False
        self.reply_text = "Bonjour!"
        self.requests = []

    async def invoke(self, request):
        self.calls += 1
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("provider failed")
        return ReplyDecision("ignore", "") if self.ignore else ReplyDecision("reply", self.reply_text)

    async def stream(self, request):
        yield AgentStreamEvent("text", text="Bonjour")
        yield AgentStreamEvent("result", result=await self.invoke(request))


def fake_provider(modem, agent):
    provider = Provider(scope=Scope.APP)
    provider.provide(lambda: modem, provides=ModemPort)
    provider.provide(lambda: agent, provides=AIAgent)
    return provider


async def poll(container):
    async with container() as scope:
        commands = await scope.get(CommandSender)
        return await commands.send(PollInbox())


async def test_mediary_di_event_to_reply_and_no_duplicate_send(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=False),
    )
    container = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(container)
        message = SmsMessage("1", "+212600000000", "bonjour", "t1")
        modem.messages = [message]
        await poll(container)
        await poll(container)
        assert modem.sends == [(message.sender, "Bonjour!")]
        assert agent.calls == 1
        store = await container.get(InboxStore)
        assert (await store.get(message.key)).state == MessageState.SENT
        modem.uncertain = True
        other = SmsMessage("2", message.sender, "hello", "t2")
        modem.messages.append(other)
        await poll(container)
        await poll(container)
        assert len(modem.sends) == 2
        assert (await store.get(other.key)).state == MessageState.UNCERTAIN
    finally:
        await container.close()


async def test_dry_run_and_bounded_generation_retries(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=True, max_attempts=2),
    )
    container = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(container)
        message = SmsMessage("1", "+212600000000", "bonjour", "t1")
        modem.messages = [message]
        await poll(container)
        store = await container.get(InboxStore)
        assert (await store.get(message.key)).state == MessageState.DRY_RUN
        assert modem.sends == []
        agent.fail = True
        other = SmsMessage("2", message.sender, "hi", "t2")
        modem.messages.append(other)
        await poll(container)
        assert (await store.get(other.key)).state == MessageState.PENDING
        await poll(container)
        await poll(container)
        assert (await store.get(other.key)).state == MessageState.FAILED
        assert agent.calls == 3
    finally:
        await container.close()


async def test_second_process_container_cannot_recover_live_inbox(tmp_path):
    settings = Settings(_env_file=None, storage=StorageConfig(path=tmp_path / "inbox.db"))
    first = build_container(settings)
    second = build_container(settings)
    try:
        await first.get(InboxStore)
        with pytest.raises(RuntimeError, match="Another gsm-agent process"):
            await second.get(InboxStore)
    finally:
        await second.close()
        await first.close()


async def test_alphanumeric_sender_is_ignored_without_generation_retries(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=True),
    )
    container = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(container)
        message = SmsMessage("1", "inwi", "Carrier notification", "t1")
        modem.messages = [message]
        await poll(container)
        record = await (await container.get(InboxStore)).get(message.key)
        assert record.state == MessageState.IGNORED
        assert record.attempts == 0
        assert agent.calls == 0
        assert modem.sends == []
    finally:
        await container.close()


async def test_news_question_ignored_by_port_still_sends_fallback(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    agent.ignore = True
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=False),
    )
    container = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(container)
        message = SmsMessage("1", "+212600000000", "What are the latest news?", "t1")
        modem.messages = [message]
        await poll(container)
        record = await (await container.get(InboxStore)).get(message.key)
        assert record.state == MessageState.SENT
        assert record.reply
        assert len(modem.sends) >= 1
        await poll(container)
        assert agent.calls == 1
    finally:
        await container.close()


async def test_phone_threads_include_sent_replies_and_survive_restart(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=False),
    )
    container = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(container)
        first = SmsMessage("1", "00212600000000", "My name is Sam", "t1")
        modem.messages = [first]
        await poll(container)
        second = SmsMessage("2", "+212600000000", "What is my name?", "t2")
        modem.messages.append(second)
        await poll(container)
        assert agent.requests[-1].thread_id == "+212600000000"
        assert agent.requests[-1].messages == (
            ChatMessage("user", first.content),
            ChatMessage("assistant", "Bonjour!"),
            ChatMessage("user", second.content),
        )
        other = SmsMessage("3", "+212611111111", "Another sender", "t3")
        modem.messages.append(other)
        await poll(container)
        assert agent.requests[-1].messages == (ChatMessage("user", other.content),)
    finally:
        await container.close()
    restarted = build_container(settings, fake_provider(modem, agent))
    try:
        third = SmsMessage("4", second.sender, "Do you still remember?", "t4")
        modem.messages.append(third)
        await poll(restarted)
        history = agent.requests[-1].messages
        assert history[0].content == first.content
        assert len(history) == 5
        assert history[-1].content == third.content
        assert all(m.content != "Another sender" for m in history)
    finally:
        await restarted.close()


async def test_partial_sends_record_only_confirmed_text_and_never_retry(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    modem.uncertain_at = 2
    agent.reply_text = "**Hello!** " * 30
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=False),
    )
    container = build_container(settings, fake_provider(modem, agent))
    message = SmsMessage("1", "+212600000000", "Please answer", "t1")
    try:
        await poll(container)
        modem.messages = [message]
        await poll(container)
        store = await container.get(InboxStore)
        record = await store.get(message.key)
        assert record.state == MessageState.UNCERTAIN
        assert len(record.reply_parts) == 2
        assert record.sent_parts == 1
        assert "**" not in record.reply
        conversations = await container.get(ConversationStore)
        history = await conversations.history(message.sender, MemoryLimits())
        assert history[-1] == ChatMessage("assistant", delivered_text(record.reply_parts[:1]))
        await poll(container)
        assert len(modem.sends) == 2
    finally:
        await container.close()
    restarted = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(restarted)
        assert len(modem.sends) == 2
        assert (await (await restarted.get(InboxStore)).get(message.key)).sent_parts == 1
    finally:
        await restarted.close()


async def test_dry_run_memory_does_not_claim_unsent_replies(tmp_path):
    modem, agent = FakeModem(), FakeAgent()
    settings = Settings(
        _env_file=None,
        storage=StorageConfig(path=tmp_path / "inbox.db"),
        listener=ListenerConfig(auto_reply=True, dry_run=True),
    )
    container = build_container(settings, fake_provider(modem, agent))
    try:
        await poll(container)
        first = SmsMessage("1", "+212600000000", "first", "t1")
        second = SmsMessage("2", first.sender, "second", "t2")
        # The modem returns newest first; processing must still be oldest first.
        modem.messages = [second, first]
        await poll(container)
        assert agent.requests[0].messages[-1].content == "first"
        assert agent.requests[1].messages == (ChatMessage("user", "first"), ChatMessage("user", "second"))
        assert modem.sends == []
    finally:
        await container.close()
