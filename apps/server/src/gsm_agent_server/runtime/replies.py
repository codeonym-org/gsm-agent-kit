import asyncio
import logging

from dishka import AsyncContainer
from gsm_agent.application.commands.process_reply import ProcessNextReply
from gsm_agent.application.runtime import WorkerId
from mediary.cqrs import CommandSender

from gsm_agent_server.infra.runtime import RuntimeMonitor, worker_issue
from gsm_agent_server.runtime.settings import AssistantSettings

logger = logging.getLogger(__name__)


async def process_replies(container: AsyncContainer, settings: AssistantSettings) -> None:
    monitor = await container.get(RuntimeMonitor)
    while True:
        monitor.begin(WorkerId.REPLIES)
        try:
            async with container() as scope:
                commands = await scope.get(CommandSender)
                await commands.send(ProcessNextReply())
            monitor.succeeded(WorkerId.REPLIES)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            monitor.failed(WorkerId.REPLIES, worker_issue(exc))
            logger.warning("Reply worker failed (%s)", type(exc).__name__)
        await asyncio.sleep(settings.poll_interval_seconds)
