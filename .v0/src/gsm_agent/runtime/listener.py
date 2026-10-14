import asyncio
import logging

from dishka import AsyncContainer
from mediary.cqrs import CommandSender

from gsm_agent.application.commands.poll_inbox import PollInbox
from gsm_agent.runtime.config import ListenerConfig

logger = logging.getLogger(__name__)


async def listen(container: AsyncContainer, config: ListenerConfig) -> None:
    failures = 0
    while True:
        try:
            async with container() as scope:
                commands = await scope.get(CommandSender)
                await commands.send(PollInbox())
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            logger.warning("Inbox poll failed (%s); retrying", type(exc).__name__)
        delay = min(60, config.poll_interval * 2 ** min(failures, 4))
        await asyncio.sleep(delay)
