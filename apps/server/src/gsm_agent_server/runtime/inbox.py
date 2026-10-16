import asyncio
import logging

from dishka import AsyncContainer
from gsm_agent.application.commands.ingest_inbox import IngestInbox
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent_core.capabilities.catalog import SMS_INBOX_READ
from mediary.cqrs import CommandSender

from gsm_agent_server.runtime.settings import InboxSettings

logger = logging.getLogger(__name__)


async def poll_inboxes(container: AsyncContainer, settings: InboxSettings) -> None:
    devices = await container.get(DeviceDirectory)
    while True:
        for device in devices.devices():
            if device.get(SMS_INBOX_READ) is None:
                continue
            try:
                async with container() as scope:
                    commands = await scope.get(CommandSender)
                    await commands.send(IngestInbox(device.device_id))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # No exception strings, provider responses, sender or SMS body in logs.
                logger.warning(
                    "Inbox poll failed for device %s (%s)", device.device_id.value, type(exc).__name__
                )
        await asyncio.sleep(settings.poll_interval_seconds)
