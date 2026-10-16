"""Canonical typed keys and immutable capability bindings."""

from dataclasses import dataclass
from typing import Final, Generic, TypeVar, cast

from gsm_agent_core.capabilities.status import DeviceStatusReader
from gsm_agent_core.domain.devices import CapabilityId

P_co = TypeVar("P_co", covariant=True)


@dataclass(frozen=True, slots=True, eq=False)
class CapabilityKey(Generic[P_co]):
    id: CapabilityId
    port_type: type[P_co]


DEVICE_STATUS_READ: CapabilityKey[DeviceStatusReader] = CapabilityKey(
    CapabilityId.DEVICE_STATUS_READ, DeviceStatusReader
)
CAPABILITIES: Final[tuple[CapabilityKey[object], ...]] = (DEVICE_STATUS_READ,)


@dataclass(frozen=True, slots=True)
class CapabilityBinding(Generic[P_co]):
    key: CapabilityKey[P_co]
    port: P_co

    def __post_init__(self) -> None:
        if self.key not in CAPABILITIES:
            raise ValueError("Use a canonical capability key from the global catalog")
        if not isinstance(self.port, self.key.port_type):
            raise TypeError(f"Port does not implement {self.key.id}")


class CapabilitySet:
    """Lookup performs no I/O; support is fixed for this opened device's lifetime."""

    def __init__(self, *bindings: CapabilityBinding[object]) -> None:
        self._bindings = {binding.key.id: binding for binding in bindings}
        if len(self._bindings) != len(bindings):
            raise ValueError("A capability cannot be bound twice")

    @property
    def supported(self) -> tuple[CapabilityId, ...]:
        return tuple(sorted(self._bindings))

    def get[P](self, key: CapabilityKey[P]) -> P | None:
        binding = self._bindings.get(key.id)
        if binding is None or binding.key is not key:
            return None
        # The binding checked the port when constructed. Consumers never cast.
        return cast(P, binding.port)
