from typing import Protocol, runtime_checkable

from gsm_agent_core.domain.submission import PreparedSms, SmsSendConstraints, SmsSubmissionResult


@runtime_checkable
class SmsSender(Protocol):
    @property
    def constraints(self) -> SmsSendConstraints: ...

    async def submit(self, sms: PreparedSms) -> SmsSubmissionResult:
        """Submit once, without silent truncation or retries; cancellation propagates."""
        ...
