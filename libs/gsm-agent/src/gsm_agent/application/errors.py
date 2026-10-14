from gsm_agent_core.domain.devices import CapabilityId, CellularDeviceId


class DeviceNotFoundError(Exception):
    def __init__(self, device_id: CellularDeviceId) -> None:
        super().__init__("Unknown logical cellular device")
        self.device_id = device_id


class UnsupportedCapabilityError(Exception):
    def __init__(self, capability: CapabilityId) -> None:
        super().__init__("Cellular device does not support this capability")
        self.capability = capability


class DeviceQueryTimeoutError(Exception):
    """The read budget expired; no successful observation was obtained."""
