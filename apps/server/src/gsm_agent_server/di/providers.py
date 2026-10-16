from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from gsm_agent.application.inbox import InboxDisabledError, InboxPolicy, IngestionCoordinator
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.queries.devices import DeviceQueryPolicy
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.ports import CellularDevice

from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.runtime.settings import DeviceSettings, Settings


class DeviceProvider(Provider):
    scope = Scope.APP

    @provide
    def inbox_policy(self, settings: Settings) -> InboxPolicy:
        return InboxPolicy(settings.inbox.timeout_seconds)

    @provide
    def ingestion_coordinator(self) -> IngestionCoordinator:
        return IngestionCoordinator()

    @provide
    async def inbox_store(self, settings: Settings) -> AsyncIterator[InboxStore]:
        if not settings.inbox.enabled:
            raise InboxDisabledError("Inbox ingestion is disabled; enable GSM_INBOX__ENABLED")
        try:
            from gsm_agent_sqlite import SqliteInboxStore
        except ImportError as exc:
            raise RuntimeError("Install gsm-agent-server[inbox] for durable inbox ingestion") from exc
        store = await SqliteInboxStore.open(settings.inbox.database_path)
        try:
            yield store
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
                ),
            )
        from gsm_agent_simulated import SimulatedDevice

        return SimulatedDevice(CellularDeviceId(config.id), availability=config.simulated_availability)
    except ImportError as exc:
        raise RuntimeError(f"Install gsm-agent-server[{config.adapter}] to use this adapter") from exc
