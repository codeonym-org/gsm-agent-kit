import logging
from dataclasses import dataclass

from mediary.cqrs import Command, EventPublisher, command, command_handler

from gsm_agent.application.events.sms_received import SmsReceived
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.modem import ModemPort
from gsm_agent.domain.sms import ReplyPolicy

logger = logging.getLogger(__name__)


@command
@dataclass(frozen=True)
class PollInbox(Command[int]):
    pass


@command_handler
class PollInboxHandler:
    def __init__(self, modem: ModemPort, inbox: InboxStore, publisher: EventPublisher, policy: ReplyPolicy):
        self.modem = modem
        self.inbox = inbox
        self.publisher = publisher
        self.policy = policy

    async def handle(self, command: PollInbox) -> int:
        messages = await self.modem.list_messages()
        added = await self.inbox.ingest(messages, self.policy.enabled)
        if self.policy.enabled:
            for record in await self.inbox.work():
                try:
                    await self.publisher.publish(SmsReceived(record.message.key))
                except Exception:
                    # One failed message must not prevent other messages being handled.
                    logger.error("SMS processing failed for key %s", record.message.key)
        return added
