import re
from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceCode:
    value: str = "*120*30#"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\*[0-9*]{1,30}#", self.value):
            raise ValueError("Balance code must be a USSD code such as *120*30#")


@dataclass(frozen=True)
class BalanceResult:
    code: str
    text: str
    checked_at: str
    session_open: bool = False
