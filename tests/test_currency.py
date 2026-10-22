"""
Test conversion between YNAB milliunits and currency amounts.
"""

from decimal import Decimal

import pytest

from currency import currency_to_milliunits, milliunits_to_currency, optional_currency


@pytest.mark.parametrize(
    ("milliunits", "amount"),
    [
        (123_456, Decimal("123.456")),
        (1, Decimal("0.001")),
        (999, Decimal("0.999")),
        (0, Decimal("0")),
        (-50_000, Decimal("-50")),
        (999_999_999, Decimal("999999.999")),
    ],
)
def test_milliunits_and_currency_convert_both_ways(
    milliunits: int, amount: Decimal
) -> None:
    assert milliunits_to_currency(milliunits) == amount
    assert currency_to_milliunits(amount) == milliunits


def test_optional_currency_keeps_a_missing_amount() -> None:
    assert optional_currency(None) is None
    assert optional_currency(2_500) == Decimal("2.5")
