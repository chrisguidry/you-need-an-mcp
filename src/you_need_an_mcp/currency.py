"""
Conversion between YNAB milliunits and currency amounts.

YNAB stores every amount as an integer number of milliunits, where 1000
milliunits are one unit of the plan's currency.  Tools speak in currency
amounts so that a model never has to do that arithmetic itself.
"""

from decimal import Decimal


def milliunits_to_currency(milliunits: int) -> Decimal:
    """Convert YNAB milliunits to a currency amount."""
    return Decimal(milliunits) / Decimal("1000")


def optional_currency(milliunits: int | None) -> Decimal | None:
    """Convert YNAB milliunits to a currency amount, keeping a missing value."""
    if milliunits is None:
        return None
    return milliunits_to_currency(milliunits)


def currency_to_milliunits(amount: Decimal) -> int:
    """Convert a currency amount to YNAB milliunits."""
    return int(amount * 1000)
