from typing import Protocol, runtime_checkable

from gsm_agent_core.domain.sms import InboxSnapshot


@runtime_checkable
class SmsInbox(Protocol):
    async def scan(self) -> InboxSnapshot:
        """Read the full declared scope without marking read or deleting.

        Include incomplete observations for baselining, never as replyable messages.
        Raise InboxReadError if any page fails; a partial scan is not a snapshot.
        """
        ...
