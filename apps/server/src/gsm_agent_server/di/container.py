from dishka import AsyncContainer, Provider, Scope, make_async_container
from mediary import Mediator

from gsm_agent_server.di.providers import DeviceProvider
from gsm_agent_server.runtime.settings import Settings


def build_container(settings: Settings, *overrides: Provider) -> AsyncContainer:
    from mediary.ext.dishka import MediaryProvider

    mediator = Mediator()
    mediator.scan("gsm_agent.application.queries")
    mediator.scan("gsm_agent.application.commands")
    if settings.assistant.enabled:
        mediator.scan("gsm_agent.application.events")
    config = Provider(scope=Scope.APP)
    config.from_context(provides=Settings)
    return make_async_container(
        config, MediaryProvider(mediator), DeviceProvider(), *overrides, context={Settings: settings}
    )
