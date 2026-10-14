import fcntl
import os
from collections.abc import AsyncIterator

import httpx
from dishka import AnyOf, Provider, Scope, provide

from gsm_agent.application.ports.ai_agent import AIAgent
from gsm_agent.application.ports.conversations import ConversationStore
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.modem import ModemPort
from gsm_agent.application.ports.text_normalizer import TextNormalizer
from gsm_agent.domain.balance import BalanceCode
from gsm_agent.domain.sms import ReplyPolicy
from gsm_agent.domain.sms_text import MemoryLimits, ReplyLimits
from gsm_agent.infra.ai.langchain_agent import LangChainAgent
from gsm_agent.infra.modem.zte import ZteModem
from gsm_agent.infra.persistence.sqlite_inbox import SqliteInbox
from gsm_agent.infra.text.plain_text import PlainTextNormalizer
from gsm_agent.runtime.settings import Settings


class AppProvider(Provider):
    scope = Scope.APP

    @provide
    async def modem(self, settings: Settings) -> AsyncIterator[ModemPort]:
        config = settings.modem
        async with httpx.AsyncClient(
            base_url=config.url.rstrip("/"),
            timeout=config.timeout,
            trust_env=False,
            headers={"Referer": config.url.rstrip("/") + "/index.html"},
        ) as client:
            yield ZteModem(
                client,
                page_size=config.page_size,
                max_pages=config.max_pages,
                send_timeout=config.send_timeout,
                ussd_timeout=config.ussd_timeout,
            )

    @provide(provides=AnyOf[InboxStore, ConversationStore])
    async def inbox(self, settings: Settings) -> AsyncIterator[SqliteInbox]:
        path = settings.storage.path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Hold across recovery + listener lifetime. A second worker using this
        # database must not turn a live send into uncertain or reply twice.
        with path.with_suffix(path.suffix + ".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another gsm-agent process owns this inbox; use one worker") from exc
            inbox = await SqliteInbox.open(path)
            try:
                yield inbox
            finally:
                await inbox.close()

    @provide
    def agent(self, settings: Settings, normalizer: TextNormalizer, limits: ReplyLimits) -> AIAgent:
        config = settings.agent
        return LangChainAgent(
            model=config.model,
            instructions=config.instructions,
            timeout=config.timeout,
            api_key=config.api_key.get_secret_value() if config.api_key else os.getenv("OPENROUTER_API_KEY"),
            base_url=config.base_url,
            normalizer=normalizer,
            limits=limits,
            max_output_tokens=config.max_output_tokens,
        )

    @provide
    def normalizer(self) -> TextNormalizer:
        return PlainTextNormalizer()

    @provide
    def reply_limits(self, settings: Settings) -> ReplyLimits:
        return ReplyLimits(settings.agent.max_reply_chars, settings.agent.max_sms_parts)

    @provide
    def memory_limits(self, settings: Settings) -> MemoryLimits:
        return MemoryLimits(settings.agent.history_messages, settings.agent.history_chars)

    @provide
    def balance_code(self, settings: Settings) -> BalanceCode:
        return BalanceCode(settings.modem.balance_code)

    @provide
    def policy(self, settings: Settings) -> ReplyPolicy:
        config = settings.listener
        return ReplyPolicy(config.auto_reply, config.dry_run, config.max_attempts)
