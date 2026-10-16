from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from gsm_agent_core.domain.balance import BalanceCarrier, BalanceObservation, CreditBalance, SmsAllowance


@pytest.mark.parametrize("text", ["", "  ", "x" * 8193, "bad\x00text", "bad\ud800text"])
def test_malformed_carrier_text_is_rejected(text):
    with pytest.raises(ValueError):
        BalanceObservation(text, datetime.now(UTC))


def test_balance_requires_timezone_and_never_invents_unknown_values():
    with pytest.raises(ValueError):
        BalanceObservation("raw", datetime(2026, 1, 1))
    observation = BalanceObservation("raw", datetime.now(UTC))
    assert observation.credit is None and observation.sms_allowance is None
    assert BalanceCarrier.INWI.consultation_code == "*120*30#"
    assert BalanceCarrier.SIMULATED.consultation_code is None


def test_explicit_zero_is_valid_but_invalid_parsed_values_are_rejected():
    assert CreditBalance(Decimal("0"), "MAD").amount == 0
    assert SmsAllowance(0).remaining == 0
    for amount in ("-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            CreditBalance(Decimal(amount), "MAD")
    for currency in ("", "mad", "M1D", "DOLLAR"):
        with pytest.raises(ValueError):
            CreditBalance(Decimal("1"), currency)
    for count in (-1, True, 0.5):
        with pytest.raises(ValueError):
            SmsAllowance(cast(int, count))
