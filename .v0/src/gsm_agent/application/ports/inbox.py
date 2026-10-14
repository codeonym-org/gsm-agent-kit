from typing import Protocol

from gsm_agent.domain.sms import InboxRecord, MessageState, SmsMessage


class InboxStore(Protocol):
    async def ingest(self, messages: list[SmsMessage], enabled: bool) -> int:
        """Atomically baseline first snapshot; insert later messages once."""
        ...

    async def work(self) -> list[InboxRecord]: ...

    async def get(self, key: str) -> InboxRecord | None: ...

    async def claim(self, key: str, expected: MessageState, state: MessageState) -> bool: ...

    async def update(
        self,
        key: str,
        state: MessageState,
        *,
        reply: str | None = None,
        error: str | None = None,
        increment_attempts: bool = False,
        reply_parts: tuple[str, ...] | None = None,
    ) -> None: ...

    async def confirm_part(self, key: str, thread_id: str, text: str) -> None:
        """Atomically record an acknowledged part and update delivered reply memory."""
        ...

    async def list_records(self, limit: int) -> list[InboxRecord]: ...
