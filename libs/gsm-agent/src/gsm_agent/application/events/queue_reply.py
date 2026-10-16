from mediary.cqrs import event_handler

from gsm_agent.application.events.sms_received import SmsReceived
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.replies import ReplyPolicy, reply_destination


@event_handler
class QueueReplyHandler:
    def __init__(self, inbox: InboxStore, replies: ReplyStore, policy: ReplyPolicy) -> None:
        self.inbox, self.replies, self.policy = inbox, replies, policy

    async def handle(self, event: SmsReceived) -> None:
        record = await self.inbox.get(event.record_id)
        if not self.policy.enabled or record is None or not record.replyable:
            return
        destination = reply_destination(record, self.policy.default_region)
        if destination is not None:
            await self.replies.enqueue(record, destination)
