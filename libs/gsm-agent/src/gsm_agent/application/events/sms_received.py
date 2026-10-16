from dataclasses import dataclass

from mediary.cqrs import Event, event


@event
@dataclass(frozen=True)
class SmsReceived(Event):
    record_id: str
