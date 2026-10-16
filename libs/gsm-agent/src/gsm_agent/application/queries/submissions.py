from dataclasses import dataclass
from uuid import UUID

from gsm_agent_core.domain.devices import CellularDeviceId
from mediary.cqrs import Query, query, query_handler

from gsm_agent.application.ports.devices import DeviceDirectory
from gsm_agent.application.ports.submissions import SubmissionStore
from gsm_agent.application.submissions import SubmissionNotFoundError, SubmissionRecord


@query
@dataclass(frozen=True)
class GetSubmission(Query[SubmissionRecord]):
    device_id: CellularDeviceId
    request_id: UUID


@query_handler
class GetSubmissionHandler:
    def __init__(self, devices: DeviceDirectory, submissions: SubmissionStore) -> None:
        self.devices, self.submissions = devices, submissions

    async def handle(self, request: GetSubmission) -> SubmissionRecord:
        self.devices.get(request.device_id)
        record = await self.submissions.get(request.device_id, request.request_id)
        if record is None:
            raise SubmissionNotFoundError("Unknown SMS submission")
        return record
