"""
Test utility functions in server module.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

import server


def test_decimal_precision_milliunits_conversion() -> None:
    """Test that milliunits conversion maintains Decimal precision."""
    # Test various milliunits values that could lose precision with floats
    test_cases = [
        (123456, Decimal("123.456")),  # Regular amount
        (1, Decimal("0.001")),  # Smallest unit
        (999, Decimal("0.999")),  # Just under 1
        (1000, Decimal("1")),  # Exactly 1
        (1001, Decimal("1.001")),  # Just over 1
        (999999999, Decimal("999999.999")),  # Large amount
        (-50000, Decimal("-50")),  # Negative amount
        (0, Decimal("0")),  # Zero
    ]

    for milliunits, expected in test_cases:
        from models import milliunits_to_currency

        result = milliunits_to_currency(milliunits)
        assert result == expected, (
            f"Failed for {milliunits}: got {result}, expected {expected}"
        )
        # Ensure result is actually a Decimal, not float
        assert isinstance(result, Decimal), (
            f"Result {result} is not a Decimal but {type(result)}"
        )


def test_milliunits_to_currency_valid_input() -> None:
    """Test milliunits conversion with valid input."""
    from models import milliunits_to_currency

    result = milliunits_to_currency(123456)
    assert result == Decimal("123.456")


def test_milliunits_to_currency_none_input() -> None:
    """Test milliunits conversion with None input raises TypeError."""
    with pytest.raises(TypeError):
        from models import milliunits_to_currency

        milliunits_to_currency(None)  # type: ignore


def test_milliunits_to_currency_zero() -> None:
    """Test milliunits conversion with zero."""
    from models import milliunits_to_currency

    result = milliunits_to_currency(0)
    assert result == Decimal("0")


def test_milliunits_to_currency_negative() -> None:
    """Test milliunits conversion with negative value."""
    from models import milliunits_to_currency

    result = milliunits_to_currency(-50000)
    assert result == Decimal("-50")


def test_convert_month_to_date_with_date_object() -> None:
    """Test convert_month_to_date with date object returns unchanged."""
    test_date = date(2024, 3, 15)
    result = server.convert_month_to_date(test_date)
    assert result == test_date


def test_convert_month_to_date_with_current() -> None:
    """Test convert_month_to_date with 'current' returns current month date."""
    with patch("server.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 9, 20, 16, 45, 0)

        result = server.convert_month_to_date("current")
        assert result == date(2024, 9, 1)


def test_convert_month_to_date_with_last_and_next() -> None:
    """Test convert_month_to_date with 'last' and 'next' literals."""
    # Test normal month (June -> May and July)
    with patch("server.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 6, 15, 10, 30, 0)

        result_last = server.convert_month_to_date("last")
        assert result_last == date(2024, 5, 1)

        result_next = server.convert_month_to_date("next")
        assert result_next == date(2024, 7, 1)

    # Test January edge case (January -> December previous year)
    with patch("server.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 1, 10, 14, 45, 0)

        result_last = server.convert_month_to_date("last")
        assert result_last == date(2023, 12, 1)

        result_next = server.convert_month_to_date("next")
        assert result_next == date(2024, 2, 1)

    # Test December edge case (December -> January next year)
    with patch("server.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2024, 12, 25, 9, 15, 0)

        result_last = server.convert_month_to_date("last")
        assert result_last == date(2024, 11, 1)

        result_next = server.convert_month_to_date("next")
        assert result_next == date(2025, 1, 1)


def test_convert_month_to_date_invalid_value() -> None:
    """Test convert_month_to_date with invalid value raises error."""
    with pytest.raises(ValueError, match="Invalid month value: invalid"):
        server.convert_month_to_date("invalid")  # type: ignore[arg-type]


def test_convert_transaction_to_model_basic() -> None:
    """Test Transaction.from_ynab with basic transaction."""
    import ynab

    from models import Transaction

    txn = ynab.TransactionDetail(
        id="txn-123",
        date=date(2024, 6, 15),
        amount=-50000,
        memo="Test transaction",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=ynab.TransactionFlagColor.RED,
        account_id="acc-1",
        payee_id="payee-1",
        category_id="cat-1",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        account_name="Checking",
        payee_name="Test Payee",
        category_name="Test Category",
        subtransactions=[],
    )

    result = Transaction.from_ynab(txn)

    assert result.id == "txn-123"
    assert result.date == date(2024, 6, 15)
    assert result.amount == Decimal("-50")
    assert result.account_name == "Checking"
    assert result.payee_name == "Test Payee"
    assert result.category_name == "Test Category"
    assert result.subtransactions is None


def test_convert_transaction_to_model_without_optional_attributes() -> None:
    """Test Transaction.from_ynab with minimal TransactionDetail."""
    import ynab

    from models import Transaction

    minimal_txn = ynab.TransactionDetail(
        id="txn-456",
        date=date(2024, 6, 16),
        amount=-25000,
        memo="Minimal transaction",
        cleared=ynab.TransactionClearedStatus.UNCLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-2",
        payee_id="payee-2",
        category_id="cat-2",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        account_name="Test Account 2",
        payee_name="Test Payee 2",
        category_name="Test Category 2",
        subtransactions=[],
    )

    result = Transaction.from_ynab(minimal_txn)

    assert result.id == "txn-456"
    assert result.account_name == "Test Account 2"
    assert result.payee_name == "Test Payee 2"
    assert result.category_name == "Test Category 2"


def test_milliunits_to_currency_from_models() -> None:
    """Test milliunits_to_currency function from models module."""
    from models import milliunits_to_currency

    assert milliunits_to_currency(50000) == Decimal("50")
    assert milliunits_to_currency(-25000) == Decimal("-25")
    assert milliunits_to_currency(1000) == Decimal("1")
    assert milliunits_to_currency(0) == Decimal("0")
