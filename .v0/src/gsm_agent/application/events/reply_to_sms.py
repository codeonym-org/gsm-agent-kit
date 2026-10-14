import logging

from mediary.cqrs import CommandSender, event_handler

from gsm_agent.application.commands.send_sms import SendSmsPart
from gsm_agent.application.events.sms_received import SmsReceived
from gsm_agent.application.ports.ai_agent import AIAgent
from gsm_agent.application.ports.conversations import ConversationStore
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.text_normalizer import TextNormalizer
from gsm_agent.domain.agent import AgentInput, ChatMessage, require_answer
from gsm_agent.domain.errors import SmsSendFailedError
from gsm_agent.domain.sms import MessageState, PhoneNumber, ReplyPolicy
from gsm_agent.domain.sms_text import MemoryLimits, ReplyLimits, delivered_text, plan_sms

logger = logging.getLogger(__name__)


@event_handler
class ReplyToSms:
    def __init__(
        self,
        agent: AIAgent,
        inbox: InboxStore,
        commands: CommandSender,
        policy: ReplyPolicy,
        conversations: ConversationStore,
        normalizer: TextNormalizer,
        limits: ReplyLimits,
        memory_limits: MemoryLimits,
    ):
        self.agent = agent
        self.inbox = inbox
        self.commands = commands
        self.policy = policy
        self.conversations = conversations
        self.normalizer = normalizer
        self.limits = limits
        self.memory_limits = memory_limits

    async def handle(self, event: SmsReceived) -> None:
        record = await self.inbox.get(event.key)
        if not record or not self.policy.enabled:
            return
        if record.state == MessageState.PENDING:
            try:
                thread_id = PhoneNumber(record.message.sender).value
            except ValueError:
                await self.inbox.update(event.key, MessageState.IGNORED, error="NonReplyableSender")
                logger.info("SMS %s ignored: non-replyable sender", event.key[:12])
                return
            if not await self.inbox.claim(event.key, MessageState.PENDING, MessageState.PROCESSING):
                return
            try:
                await self.conversations.remember(
                    thread_id, event.key, ChatMessage("user", record.message.content)
                )
                history = await self.conversations.history(
                    thread_id, self.memory_limits, through_key=event.key
                )
                decision = require_answer(await self.agent.invoke(AgentInput(history, thread_id=thread_id)))
                plan = (
                    plan_sms(self.normalizer.normalize(decision.text), self.limits)
                    if decision.action == "reply"
                    else None
                )
            except Exception as exc:
                attempts = record.attempts + 1
                state = MessageState.FAILED if attempts >= self.policy.max_attempts else MessageState.PENDING
                await self.inbox.update(event.key, state, error=type(exc).__name__, increment_attempts=True)
                cause = exc.__cause__ or exc
                logger.warning(
                    "SMS %s generation failed: error=%s cause=%s attempt=%s state=%s",
                    event.key[:12],
                    type(exc).__name__,
                    type(cause).__name__,
                    attempts,
                    state.value,
                )
                return
            if decision.action == "ignore":
                await self.inbox.update(event.key, MessageState.IGNORED)
                logger.info("SMS %s ignored: reason=%s", event.key[:12], decision.ignore_reason)
                return
            await self.inbox.update(event.key, MessageState.PLANNED, reply=plan.text, reply_parts=plan.parts)
            record = await self.inbox.get(event.key)
        if record is None or record.state != MessageState.PLANNED:
            return
        # Older databases may have planned replies without a segment plan.
        # Prepare them before taking the irreversible send claim.
        plan = plan_sms(self.normalizer.normalize(record.reply or ""), self.limits)
        parts = plan.parts
        if parts != record.reply_parts:
            await self.inbox.update(event.key, MessageState.PLANNED, reply=plan.text, reply_parts=parts)
        if not await self.inbox.claim(event.key, MessageState.PLANNED, MessageState.SENDING):
            return
        try:
            thread_id = PhoneNumber(record.message.sender).value
            for index in range(record.sent_parts, len(parts)):
                receipt = await self.commands.send(SendSmsPart(record.message.sender, parts[index]))
                if receipt.state == MessageState.SENT:
                    await self.inbox.confirm_part(event.key, thread_id, delivered_text(parts[: index + 1]))
        except SmsSendFailedError as exc:
            await self.inbox.update(event.key, MessageState.FAILED, error=type(exc).__name__)
            logger.warning("SMS %s send failed: error=%s", event.key[:12], type(exc).__name__)
        except Exception as exc:
            # Even a connection timeout may mean the modem sent the SMS.
            await self.inbox.update(event.key, MessageState.UNCERTAIN, error=type(exc).__name__)
            logger.warning("SMS %s send outcome uncertain: error=%s", event.key[:12], type(exc).__name__)
        else:
            state = MessageState.DRY_RUN if self.policy.dry_run else MessageState.SENT
            await self.inbox.update(event.key, state)
            logger.info("SMS %s reply completed: state=%s parts=%s", event.key[:12], state.value, len(parts))
