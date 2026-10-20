from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from gsm_agent.application.inbox import InboxDisabledError, InboxPolicy, IngestionCoordinator
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.ports.submissions import SubmissionStore
from gsm_agent.application.queries.balance import BalancePolicy
from gsm_agent.application.queries.devices import DeviceQueryPolicy
from gsm_agent.application.replies import ReplyCoordinator, ReplyPolicy
from gsm_agent.application.submissions import SubmissionCoordinator, SubmissionDisabledError, SubmissionPolicy
from gsm_agent.application.text import SmsLimits
from gsm_agent_core.ai import AIAgent
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.ports import CellularDevice

from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.infra.realtime import ChangeFeed, ObservedInbox, ObservedReplies, ObservedSubmissions
from gsm_agent_server.infra.replies import DisabledAgent, DisabledReplyStore
from gsm_agent_server.runtime.settings import DeviceSettings, Settings


class DeviceProvider(Provider):
    scope = Scope.APP

    @provide
    def change_feed(self) -> ChangeFeed:
        return ChangeFeed()

    @provide
    def balance_policy(self, settings: Settings) -> BalancePolicy:
        config = settings.balance
        return BalancePolicy(config.carrier, config.timeout_seconds, config.cleanup_timeout_seconds)

    @provide
    def reply_policy(self, settings: Settings) -> ReplyPolicy:
        config = settings.assistant
        return ReplyPolicy(
            enabled=config.enabled,
            dry_run=config.dry_run,
            default_region=config.default_region,
            timeout_seconds=config.timeout_seconds,
            history_max_messages=config.history_max_messages,
            history_max_chars=config.history_max_chars,
            history_retention_days=config.history_retention_days,
            input_max_chars=config.input_max_chars,
        )

    @provide
    def reply_coordinator(self) -> ReplyCoordinator:
        return ReplyCoordinator()

    @provide
    async def reply_store(
        self, settings: Settings, policy: ReplyPolicy, feed: ChangeFeed
    ) -> AsyncIterator[ReplyStore]:
        if not settings.assistant.enabled:
            yield DisabledReplyStore()
            return
        try:
            from gsm_agent_sqlite import SqliteReplyStore
        except ImportError as exc:
            raise RuntimeError("Install gsm-agent-server[ai] for persistent auto-replies") from exc
        store = await SqliteReplyStore.open(settings.assistant.database_path)
        try:
            await store.prune(policy)
            yield ObservedReplies(store, feed)
        finally:
            await store.close()

    @provide
    def ai_agent(self, settings: Settings) -> AIAgent:
        config = settings.assistant
        if not config.enabled:
            return DisabledAgent()
        if config.api_key is None:
            raise RuntimeError("Set GSM_ASSISTANT__API_KEY to enable the OpenRouter assistant")
        try:
            from gsm_agent_langchain import LangChainAgent
        except ImportError as exc:
            raise RuntimeError("Install gsm-agent-server[ai] for the OpenRouter assistant") from exc
        return LangChainAgent(
            model=config.model,
            api_key=config.api_key.get_secret_value(),
            instructions=config.instructions,
            max_output_tokens=config.max_output_tokens,
            max_total_chars=settings.submissions.max_total_chars,
            max_parts=settings.submissions.max_parts,
            timeout_seconds=config.timeout_seconds,
        )

    @provide
    def submission_policy(self, settings: Settings) -> SubmissionPolicy:
        config = settings.submissions
        return SubmissionPolicy(SmsLimits(config.max_total_chars, config.max_parts), config.timeout_seconds)

    @provide
    def submission_coordinator(self) -> SubmissionCoordinator:
        return SubmissionCoordinator()

    @provide
    async def submission_store(self, settings: Settings, feed: ChangeFeed) -> AsyncIterator[SubmissionStore]:
        if not settings.submissions.enabled:
            raise SubmissionDisabledError("SMS submission is disabled; enable GSM_SUBMISSIONS__ENABLED")
        try:
            from gsm_agent_sqlite import SqliteSubmissionStore
        except ImportError as exc:
            raise RuntimeError("Install gsm-agent-server[sms] for durable SMS submission") from exc
        store = await SqliteSubmissionStore.open(settings.submissions.database_path)
        try:
            yield ObservedSubmissions(store, feed)
        finally:
            await store.close()

    @provide
    def inbox_policy(self, settings: Settings) -> InboxPolicy:
        return InboxPolicy(settings.inbox.timeout_seconds)

    @provide
    def ingestion_coordinator(self) -> IngestionCoordinator:
        return IngestionCoordinator()

    @provide
    async def inbox_store(self, settings: Settings, feed: ChangeFeed) -> AsyncIterator[InboxStore]:
        if not settings.inbox.enabled:
            raise InboxDisabledError("Inbox ingestion is disabled; enable GSM_INBOX__ENABLED")
        try:
            from gsm_agent_sqlite import SqliteInboxStore
        except ImportError as exc:
            raise RuntimeError("Install gsm-agent-server[inbox] for durable inbox ingestion") from exc
        store = await SqliteInboxStore.open(settings.inbox.database_path)
        try:
            yield ObservedInbox(store, feed)
        finally:
            await store.close()

    @provide
    def query_policy(self, settings: Settings) -> DeviceQueryPolicy:
        return DeviceQueryPolicy(settings.query_timeout_seconds)

    @provide
    async def devices(self, settings: Settings) -> AsyncIterator[DeviceDirectory]:
        device = _create_device(settings.device)
        try:
            yield ConfiguredDevices((device,), (device.manifest,))
        finally:
            await device.close()


def _create_device(config: DeviceSettings) -> CellularDevice:
    # Optional imports keep a ZTE install independent of the simulated adapter.
    try:
        if config.adapter == "zte-mf833t":
            from gsm_agent_zte_mf833t import ZteMf833tDevice, ZteMf833tSettings

            connection = config.zte_mf833t
            return ZteMf833tDevice(
                CellularDeviceId(config.id),
                ZteMf833tSettings(
                    base_url=connection.base_url,
                    timeout_seconds=connection.timeout_seconds,
                    inbox_timeout_seconds=connection.inbox_timeout_seconds,
                    page_size=connection.page_size,
                    max_pages=connection.max_pages,
                    storage_generation=connection.storage_generation,
                    subscription_generation=connection.subscription_generation,
                    send_timeout_seconds=connection.send_timeout_seconds,
                    send_poll_interval_seconds=connection.send_poll_interval_seconds,
                ),
            )
        from gsm_agent_simulated import SimulatedDevice

        return SimulatedDevice(
            CellularDeviceId(config.id),
            availability=config.simulated_availability,
            balance_enabled=config.simulated_balance_enabled,
        )
    except ImportError as exc:
        raise RuntimeError(f"Install gsm-agent-server[{config.adapter}] to use this adapter") from exc
