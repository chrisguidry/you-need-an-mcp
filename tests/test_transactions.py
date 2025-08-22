"""
Tests for transaction-related functionality in YNAB MCP Server.
"""

from datetime import date
from unittest.mock import MagicMock

import ynab
from assertions import extract_response_data
from conftest import create_ynab_transaction
from fastmcp.client import Client, FastMCPTransport


async def test_list_transactions_basic(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test basic transaction listing without filters."""

    txn1 = create_ynab_transaction(
        id="txn-1",
        transaction_date=date(2024, 1, 15),
        amount=-50_000,  # -$50.00 outflow
        memo="Grocery shopping",
        flag_color=ynab.TransactionFlagColor.RED,
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Whole Foods",
        category_id="cat-1",
        category_name="Groceries",
    )

    txn2 = create_ynab_transaction(
        id="txn-2",
        transaction_date=date(2024, 1, 20),
        amount=-75_000,  # -$75.00 outflow
        memo="Dinner",
        cleared=ynab.TransactionClearedStatus.UNCLEARED,
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Restaurant XYZ",
        category_id="cat-2",
        category_name="Dining Out",
    )

    # Add a deleted transaction that should be filtered out
    txn_deleted = create_ynab_transaction(
        id="txn-deleted",
        transaction_date=date(2024, 1, 10),
        amount=-25_000,
        memo="Deleted transaction",
        account_name="Checking",
        payee_id="payee-3",
        payee_name="Store ABC",
        category_id="cat-1",
        category_name="Groceries",
        deleted=True,  # Should be excluded
    )

    # Mock repository to return transactions
    mock_repository.get_transactions.return_value = [txn2, txn1, txn_deleted]

    result = await mcp_client.call_tool("list_transactions", {})

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None

    # Should have 2 transactions (deleted one excluded)
    assert len(response_data["transactions"]) == 2

    # Should be sorted by date descending
    assert response_data["transactions"][0]["id"] == "txn-2"
    assert response_data["transactions"][0]["date"] == "2024-01-20"
    assert response_data["transactions"][0]["amount"] == "-75"
    assert response_data["transactions"][0]["payee_name"] == "Restaurant XYZ"
    assert response_data["transactions"][0]["category_name"] == "Dining Out"

    assert response_data["transactions"][1]["id"] == "txn-1"
    assert response_data["transactions"][1]["date"] == "2024-01-15"
    assert response_data["transactions"][1]["amount"] == "-50"
    assert response_data["transactions"][1]["flag"] == "Red"

    # Check pagination
    assert response_data["pagination"]["total_count"] == 2
    assert response_data["pagination"]["has_more"] is False


async def test_list_transactions_with_account_filter(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing filtered by account."""
    # Create transaction
    txn = create_ynab_transaction(
        id="txn-acc-1",
        transaction_date=date(2024, 2, 1),
        amount=-30_000,
        memo="Account filtered",
        account_id="acc-checking",
        account_name="Main Checking",
        payee_id="payee-1",
        payee_name="Store",
        category_id="cat-1",
        category_name="Shopping",
    )

    # Mock repository to return filtered transactions
    mock_repository.get_transactions_by_filters.return_value = [txn]

    result = await mcp_client.call_tool(
        "list_transactions", {"account_id": "acc-checking"}
    )

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["account_id"] == "acc-checking"

    # Verify correct repository method was called
    mock_repository.get_transactions_by_filters.assert_called_once_with(
        account_id="acc-checking",
        category_id=None,
        payee_id=None,
        since_date=None,
    )


async def test_list_transactions_with_amount_filters(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing with amount range filters."""
    # Create transactions with different amounts
    txn_small = create_ynab_transaction(
        id="txn-small",
        transaction_date=date(2024, 3, 1),
        amount=-25_000,  # -$25
        memo="Small purchase",
        payee_id="payee-1",
        payee_name="Coffee Shop",
        category_id="cat-1",
        category_name="Dining Out",
    )

    txn_medium = create_ynab_transaction(
        id="txn-medium",
        transaction_date=date(2024, 3, 2),
        amount=-60_000,  # -$60
        memo="Medium purchase",
        payee_id="payee-2",
        payee_name="Restaurant",
        category_id="cat-1",
        category_name="Dining Out",
    )

    txn_large = create_ynab_transaction(
        id="txn-large",
        transaction_date=date(2024, 3, 3),
        amount=-120_000,  # -$120
        memo="Large purchase",
        payee_id="payee-3",
        payee_name="Electronics Store",
        category_id="cat-2",
        category_name="Shopping",
    )

    # Mock repository to return all transactions for filtering
    mock_repository.get_transactions.return_value = [txn_small, txn_medium, txn_large]

    # Test with min_amount filter (transactions >= -$50)
    result = await mcp_client.call_tool(
        "list_transactions",
        {
            "min_amount": -50.0  # -$50
        },
    )

    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only include small transaction (-$25 > -$50)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["id"] == "txn-small"

    # Test with max_amount filter (transactions <= -$100)
    result = await mcp_client.call_tool(
        "list_transactions",
        {
            "max_amount": -100.0  # -$100
        },
    )

    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only include large transaction (-$120 < -$100)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["id"] == "txn-large"

    # Test with both min and max filters
    result = await mcp_client.call_tool(
        "list_transactions",
        {
            "min_amount": -80.0,  # >= -$80
            "max_amount": -40.0,  # <= -$40
        },
    )

    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only include medium transaction (-$60)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["id"] == "txn-medium"


async def test_list_transactions_with_subtransactions(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test transaction listing with split transactions (subtransactions)."""
    sub1 = ynab.SubTransaction(
        id="sub-1",
        transaction_id="txn-split",
        amount=-30_000,  # -$30
        memo="Groceries portion",
        payee_id=None,
        payee_name=None,
        category_id="cat-groceries",
        category_name="Groceries",
        transfer_account_id=None,
        transfer_transaction_id=None,
        deleted=False,
    )

    sub2 = ynab.SubTransaction(
        id="sub-2",
        transaction_id="txn-split",
        amount=-20_000,  # -$20
        memo="Household items",
        payee_id=None,
        payee_name=None,
        category_id="cat-household",
        category_name="Household",
        transfer_account_id=None,
        transfer_transaction_id=None,
        deleted=False,
    )

    # Deleted subtransaction should be filtered out
    sub_deleted = ynab.SubTransaction(
        id="sub-deleted",
        transaction_id="txn-split",
        amount=-10_000,
        memo="Deleted sub",
        payee_id=None,
        payee_name=None,
        category_id="cat-other",
        category_name="Other",
        transfer_account_id=None,
        transfer_transaction_id=None,
        deleted=True,
    )

    # Create split transaction
    txn_split = create_ynab_transaction(
        id="txn-split",
        transaction_date=date(2024, 4, 1),
        amount=-50_000,  # -$50 total
        memo="Split transaction at Target",
        payee_id="payee-target",
        payee_name="Target",
        category_id=None,  # Split transactions don't have a single category
        category_name=None,
        subtransactions=[sub1, sub2, sub_deleted],
    )

    # Mock repository to return split transaction
    mock_repository.get_transactions.return_value = [txn_split]

    result = await mcp_client.call_tool("list_transactions", {})

    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1

    txn = response_data["transactions"][0]
    assert txn["id"] == "txn-split"
    assert txn["amount"] == "-50"

    # Should have 2 subtransactions (deleted one excluded)
    assert len(txn["subtransactions"]) == 2
    assert txn["subtransactions"][0]["id"] == "sub-1"
    assert txn["subtransactions"][0]["amount"] == "-30"
    assert txn["subtransactions"][0]["category_name"] == "Groceries"
    assert txn["subtransactions"][1]["id"] == "sub-2"
    assert txn["subtransactions"][1]["amount"] == "-20"
    assert txn["subtransactions"][1]["category_name"] == "Household"


async def test_list_transactions_pagination(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test transaction listing with pagination."""
    # Create many transactions to test pagination
    transactions = []
    for i in range(5):
        txn = create_ynab_transaction(
            id=f"txn-{i}",
            transaction_date=date(2024, 1, i + 1),
            amount=-10_000 * (i + 1),
            memo=f"Transaction {i}",
            payee_id=f"payee-{i}",
            payee_name=f"Store {i}",
            category_id="cat-1",
            category_name="Shopping",
        )
        transactions.append(txn)

    # Mock repository to return all transactions
    mock_repository.get_transactions.return_value = transactions

    # Test first page
    result = await mcp_client.call_tool("list_transactions", {"limit": 2, "offset": 0})

    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 2
    assert response_data["pagination"]["total_count"] == 5
    assert response_data["pagination"]["has_more"] is True

    # Transactions should be sorted by date descending
    assert response_data["transactions"][0]["id"] == "txn-4"
    assert response_data["transactions"][1]["id"] == "txn-3"

    # Test second page
    result = await mcp_client.call_tool("list_transactions", {"limit": 2, "offset": 2})

    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 2
    assert response_data["transactions"][0]["id"] == "txn-2"
    assert response_data["transactions"][1]["id"] == "txn-1"


async def test_list_transactions_with_category_filter(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing filtered by category."""

    # Create transaction
    txn = create_ynab_transaction(
        id="txn-cat-1",
        transaction_date=date(2024, 2, 1),
        amount=-40_000,
        memo="Category filtered",
        payee_id="payee-1",
        payee_name="Store",
        category_id="cat-dining",
        category_name="Dining Out",
    )

    # Mock repository to return filtered transactions
    mock_repository.get_transactions_by_filters.return_value = [txn]

    result = await mcp_client.call_tool(
        "list_transactions", {"category_id": "cat-dining"}
    )

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["category_id"] == "cat-dining"

    # Verify correct repository method was called
    mock_repository.get_transactions_by_filters.assert_called_once_with(
        account_id=None,
        category_id="cat-dining",
        payee_id=None,
        since_date=None,
    )


async def test_list_transactions_with_payee_filter(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing filtered by payee."""
    # Create transaction
    txn = create_ynab_transaction(
        id="txn-payee-1",
        transaction_date=date(2024, 3, 1),
        amount=-80_000,
        memo="Payee filtered",
        payee_id="payee-amazon",
        payee_name="Amazon",
        category_id="cat-shopping",
        category_name="Shopping",
    )

    # Mock repository to return filtered transactions
    mock_repository.get_transactions_by_filters.return_value = [txn]

    result = await mcp_client.call_tool(
        "list_transactions", {"payee_id": "payee-amazon"}
    )

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["payee_id"] == "payee-amazon"

    # Verify correct repository method was called
    mock_repository.get_transactions_by_filters.assert_called_once_with(
        account_id=None,
        category_id=None,
        payee_id="payee-amazon",
        since_date=None,
    )
