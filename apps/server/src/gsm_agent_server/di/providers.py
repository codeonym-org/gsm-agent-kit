from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.queries.devices import DeviceQueryPolicy
from gsm_agent_core.domain.devices import CellularDeviceId

from gsm_agent_server.infra.devices import ConfiguredDevices
from gsm_agent_server.runtime.settings import Settings


class DeviceProvider(Provider):
    scope = Scope.APP

    @provide
    def query_policy(self, settings: Settings) -> DeviceQueryPolicy:
        return DeviceQueryPolicy(settings.query_timeout_seconds)

    @provide
    async def devices(self, settings: Settings) -> AsyncIterator[DeviceDirectory]:
        # Adapter packages are optional. Selecting one is explicit runtime policy.
        try:
            from gsm_agent_simulated import MANIFEST, SimulatedDevice
        except ImportError as exc:
            raise RuntimeError("Install gsm-agent-server[simulated] to use the simulated adapter") from exc

        device = SimulatedDevice(
            CellularDeviceId(settings.device.id), availability=settings.device.simulated_availability
        )
        try:
            yield ConfiguredDevices((device,), (MANIFEST,))
        finally:
            await device.close()
