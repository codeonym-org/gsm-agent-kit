import asyncio
from dataclasses import dataclass

from gsm_agent_core.capabilities.catalog import SMS_INBOX_READ
from gsm_agent_core.domain.devices import CellularDeviceId, DeviceReadIssue
from gsm_agent_core.domain.sms import InboxReadError
from mediary.cqrs import Command, EventPublisher, command, command_handler

from gsm_agent.application.errors import UnsupportedCapabilityError
from gsm_agent.application.events.sms_received import SmsReceived
from gsm_agent.application.inbox import InboxDeadlineError, InboxPolicy, IngestionCoordinator, IngestResult
from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.inbox import InboxStore


@command
@dataclass(frozen=True)
class IngestInbox(Command[IngestResult]):
    device_id: CellularDeviceId


@command_handler
class IngestInboxHandler:
    def __init__(
        self,
        devices: DeviceDirectory,
        inbox: InboxStore,
        publisher: EventPublisher,
        coordinator: IngestionCoordinator,
        policy: InboxPolicy,
    ) -> None:
        self.devices, self.inbox, self.publisher = devices, inbox, publisher
        self.coordinator, self.policy = coordinator, policy

    async def handle(self, request: IngestInbox) -> IngestResult:
        reader = self.devices.get(request.device_id).get(SMS_INBOX_READ)
        if reader is None:
            raise UnsupportedCapabilityError(SMS_INBOX_READ.id)
        try:
            async with asyncio.timeout(self.policy.timeout_seconds):
                async with self.coordinator.lock(request.device_id):
                    snapshot = await reader.scan()
                    if snapshot.source.device_id != request.device_id:
                        raise InboxReadError(DeviceReadIssue.INVALID_RESPONSE)
                    result = await self.inbox.ingest(snapshot)
                    # The transaction has committed before any handler sees the event.
                    # A crash between publish and ack can redeliver the same record ID.
                    for record_id in await self.inbox.pending_events(request.device_id):
                        await self.publisher.publish(SmsReceived(record_id))
                        await self.inbox.acknowledge_event(record_id)
                    return result
        except TimeoutError as exc:
            raise InboxDeadlineError("Inbox ingestion exceeded its deadline") from exc
