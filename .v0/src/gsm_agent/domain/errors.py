class ModemConnectionError(Exception):
    """The modem could not be read."""


class SmsSendFailedError(Exception):
    """The modem explicitly rejected the send."""


class SmsSendUncertainError(Exception):
    """The request may have been accepted; do not blindly retry."""


class AgentUnavailableError(Exception):
    """The configured AI provider could not produce a valid decision."""


class BalanceUnavailableError(Exception):
    """The modem/carrier could not complete the balance consultation."""


class BalanceTimeoutError(BalanceUnavailableError):
    """The consultation did not complete before its deadline."""
