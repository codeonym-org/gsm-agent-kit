from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.queries.devices import DeviceQueryPolicy
from gsm_agent_core.domain.devices import CellularDeviceId
from gsm_agent_core.ports import CellularDevice

from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.runtime.settings import DeviceSettings, Settings


class DeviceProvider(Provider):
    scope = Scope.APP

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
                ZteMf833tSettings(connection.base_url, connection.timeout_seconds),
            )
        from gsm_agent_simulated import SimulatedDevice

        return SimulatedDevice(CellularDeviceId(config.id), availability=config.simulated_availability)
    except ImportError as exc:
        raise RuntimeError(f"Install gsm-agent-server[{config.adapter}] to use this adapter") from exc
