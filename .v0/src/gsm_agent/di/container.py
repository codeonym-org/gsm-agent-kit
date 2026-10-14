from dishka import AsyncContainer, Provider, Scope, make_async_container
from mediary import Mediator
from mediary.ext.dishka import MediaryProvider
from mediary.ext.otel import TracingBehavior

from gsm_agent.di.providers import AppProvider
from gsm_agent.runtime.settings import Settings


def build_container(settings: Settings, *overrides: Provider) -> AsyncContainer:
    mediator = Mediator()
    mediator.scan("gsm_agent.application")
    mediator.use(TracingBehavior(), order=-1000)
    config = Provider(scope=Scope.APP)
    config.from_context(provides=Settings)
    return make_async_container(
        config, MediaryProvider(mediator), AppProvider(), *overrides, context={Settings: settings}
    )
