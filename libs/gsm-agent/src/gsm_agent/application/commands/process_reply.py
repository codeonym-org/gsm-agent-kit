import asyncio
from dataclasses import dataclass, replace

from gsm_agent_core.ai import AIAgent
from gsm_agent_core.capabilities.catalog import SMS_SEND
from gsm_agent_core.domain.agent import AgentInput, ChatMessage
from mediary.cqrs import Command, CommandSender, QuerySender, command, command_handler

from gsm_agent.application.commands.send_sms import SendSms
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore
from gsm_agent.application.ports.replies import ReplyStore
from gsm_agent.application.queries.submissions import GetSubmission
from gsm_agent.application.replies import ReplyCoordinator, ReplyPolicy, ReplyState
from gsm_agent.application.submissions import PartState, SubmissionNotFoundError, SubmissionPolicy
from gsm_agent.application.text import prepare_sms


@command
@dataclass(frozen=True)
class ProcessNextReply(Command[bool]):
    """Process at most one durable reply job. True means a job was handled."""


@command_handler
class ProcessNextReplyHandler:
    def __init__(
        self,
        inbox: InboxStore,
        replies: ReplyStore,
        agent: AIAgent,
        policy: ReplyPolicy,
        coordinator: ReplyCoordinator,
        commands: CommandSender,
        queries: QuerySender,
        devices: DeviceDirectory,
        submission_policy: SubmissionPolicy,
    ) -> None:
        self.inbox, self.replies, self.agent, self.policy = inbox, replies, agent, policy
        self.coordinator, self.commands, self.queries = coordinator, commands, queries
        self.devices, self.submission_policy = devices, submission_policy

    async def handle(self, request: ProcessNextReply) -> bool:
        if not self.policy.enabled:
            return False
        async with self.coordinator.lock:
            job = await self.replies.next_job()
            if job is None:
                return False
            record = await self.inbox.get(job.record_id)
            if record is None:
                await self.replies.update(job.record_id, ReplyState.INTERRUPTED, issue="source_missing")
                return True
            user_text = record.item.body[: self.policy.input_max_chars]
            try:
                if job.state is ReplyState.SUBMITTING:
                    # Restart/cancellation reconciliation only reads the ledger. Never send again.
                    try:
                        submission = await self.queries.send(
                            GetSubmission(record.source.device_id, job.request_id)
                        )
                    except SubmissionNotFoundError:
                        await self.replies.update(
                            job.record_id, ReplyState.INTERRUPTED, issue="no_submission_evidence"
                        )
                        return True
                else:
                    if not record.replyable:
                        await self.replies.update(job.record_id, ReplyState.IGNORED, issue="source_changed")
                        return True
                    sender = self.devices.get(record.source.device_id).get(SMS_SEND)
                    if sender is None:
                        await self.replies.update(
                            job.record_id, ReplyState.IGNORED, issue="sms_send_unsupported"
                        )
                        return True
                    if job.state is ReplyState.QUEUED:
                        await self.replies.update(job.record_id, ReplyState.GENERATING)
                        history = await self.replies.history(job.conversation_key, self.policy)
                        async with asyncio.timeout(self.policy.timeout_seconds):
                            decision = await self.agent.invoke(
                                AgentInput(job.conversation_key, history + (ChatMessage("user", user_text),))
                            )
                        if decision.action == "ignore":
                            await self.replies.update(
                                job.record_id, ReplyState.IGNORED, issue=decision.ignore_reason
                            )
                            return True
                        job = replace(job, text=decision.text, state=ReplyState.PREPARED)
                        await self.replies.update(job.record_id, ReplyState.PREPARED, text=job.text)
                    # A scan may have detected a SIM/storage change while the model ran.
                    current = await self.inbox.get(job.record_id)
                    if current is None or not current.replyable:
                        await self.replies.update(job.record_id, ReplyState.IGNORED, issue="source_changed")
                        return True
                    if self.policy.dry_run:
                        plan = prepare_sms(job.text, self.submission_policy.limits, sender.constraints)
                        await self.replies.update(
                            job.record_id, ReplyState.DRY_RUN, text="\n".join(plan.parts)
                        )
                        return True
                    await self.replies.update(job.record_id, ReplyState.SUBMITTING, text=job.text)
                    job = replace(job, state=ReplyState.SUBMITTING)
                    submission = await self.commands.send(
                        SendSms(record.source.device_id, job.request_id, job.destination, job.text)
                    )
                accepted = "\n".join(
                    part.text for part in submission.parts if part.state is PartState.ACCEPTED
                )
                await self.replies.finish(
                    job,
                    ReplyState.COMPLETED if submission.complete else ReplyState.INTERRUPTED,
                    user_text,
                    accepted,
                    self.policy,
                    issue=None if submission.complete else "submission_incomplete",
                )
            except asyncio.CancelledError:
                # Leave submitting for read-only reconciliation; generation cannot send.
                if job.state is not ReplyState.SUBMITTING:
                    await asyncio.shield(
                        self.replies.update(job.record_id, ReplyState.FAILED, issue="interrupted")
                    )
                raise
            except Exception:
                # Provider payloads and user input never become exception strings or log fields.
                if job.state is ReplyState.SUBMITTING:
                    # Next drain reconciles any accepted parts; absent evidence becomes interrupted.
                    return True
                await self.replies.update(
                    job.record_id, ReplyState.FAILED, issue="agent_or_preparation_failed"
                )
            return True
