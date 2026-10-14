from dataclasses import dataclass

from mediary.cqrs import Command, command, command_handler

from gsm_agent.application.ports.modem import ModemPort
from gsm_agent.application.ports.text_normalizer import TextNormalizer
from gsm_agent.domain.sms import MessageState, PhoneNumber, ReplyPolicy, SendReceipt
from gsm_agent.domain.sms_text import ReplyLimits, plan_sms, single_sms_capacity, sms_encoding, sms_units


@command
@dataclass(frozen=True)
class SendSms(Command[SendReceipt]):
    recipient: str
    text: str


@command_handler
class SendSmsHandler:
    def __init__(
        self, modem: ModemPort, policy: ReplyPolicy, normalizer: TextNormalizer, limits: ReplyLimits
    ):
        self.modem = modem
        self.policy = policy
        self.normalizer = normalizer
        self.limits = limits

    async def handle(self, command: SendSms) -> SendReceipt:
        recipient = PhoneNumber(command.recipient)
        plan = plan_sms(self.normalizer.normalize(command.text), self.limits)
        if self.policy.dry_run:
            return SendReceipt(recipient.value, MessageState.DRY_RUN, len(plan.parts))
        for part in plan.parts:
            await self.modem.send_sms(recipient, part)
        return SendReceipt(recipient.value, MessageState.SENT, len(plan.parts))


@command
@dataclass(frozen=True)
class SendSmsPart(Command[SendReceipt]):
    """Send one already prepared segment; used with durable per-part progress."""

    recipient: str
    text: str


@command_handler
class SendSmsPartHandler:
    def __init__(self, modem: ModemPort, policy: ReplyPolicy):
        self.modem = modem
        self.policy = policy

    async def handle(self, command: SendSmsPart) -> SendReceipt:
        recipient = PhoneNumber(command.recipient)
        if not command.text.strip() or sms_units(command.text) > single_sms_capacity(
            sms_encoding(command.text)
        ):
            raise ValueError("Prepared part exceeds a single SMS segment")
        if self.policy.dry_run:
            return SendReceipt(recipient.value, MessageState.DRY_RUN)
        await self.modem.send_sms(recipient, command.text)
        return SendReceipt(recipient.value, MessageState.SENT)
