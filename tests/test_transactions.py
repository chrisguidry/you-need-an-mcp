"""
Tests for transaction-related functionality in YNAB MCP Server.

Tests the list_transactions tool with various filters and scenarios.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import ynab
from assertions import extract_response_data
from fastmcp.client import Client, FastMCPTransport


def create_ynab_transaction(
    *,
    id: str = "txn-1",
    date: date = date(2024, 1, 15),
    amount: int = -50_000,  # -$50.00
    account_id: str = "acc-1",
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.TransactionDetail:
    """Create a YNAB TransactionDetail for testing with sensible defaults."""
    return ynab.TransactionDetail(
        id=id,
        date=date,
        amount=amount,
        memo=kwargs.get("memo"),
        cleared=kwargs.get("cleared", ynab.TransactionClearedStatus.CLEARED),
        approved=kwargs.get("approved", True),
        flag_color=kwargs.get("flag_color"),
        account_id=account_id,
        account_name=kwargs.get("account_name", "Test Account"),
        payee_id=kwargs.get("payee_id"),
        payee_name=kwargs.get("payee_name"),
        category_id=kwargs.get("category_id"),
        category_name=kwargs.get("category_name"),
        transfer_account_id=kwargs.get("transfer_account_id"),
        transfer_transaction_id=kwargs.get("transfer_transaction_id"),
        matched_transaction_id=kwargs.get("matched_transaction_id"),
        import_id=kwargs.get("import_id"),
        import_payee_name=kwargs.get("import_payee_name"),
        import_payee_name_original=kwargs.get("import_payee_name_original"),
        debt_transaction_type=kwargs.get("debt_transaction_type"),
        deleted=deleted,
        subtransactions=kwargs.get("subtransactions", []),
    )


async def test_list_transactions_basic(
    transactions_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test basic transaction listing without filters."""

    txn1 = create_ynab_transaction(
        id="txn-1",
        date=date(2024, 1, 15),
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
        date=date(2024, 1, 20),
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
        date=date(2024, 1, 10),
        amount=-25_000,
        memo="Deleted transaction",
        account_name="Checking",
        payee_id="payee-3",
        payee_name="Store ABC",
        category_id="cat-1",
        category_name="Groceries",
        deleted=True,  # Should be excluded
    )

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=[txn2, txn1, txn_deleted],  # Out of order to test sorting
            server_knowledge=0,
        )
    )

    transactions_api.get_transactions.return_value = transactions_response

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
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing filtered by account."""
    # Create transaction
    txn = ynab.TransactionDetail(
        id="txn-acc-1",
        date=date(2024, 2, 1),
        amount=-30000,
        memo="Account filtered",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-checking",
        account_name="Main Checking",
        payee_id="payee-1",
        payee_name="Store",
        category_id="cat-1",
        category_name="Shopping",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[],
    )

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(transactions=[txn], server_knowledge=0)
    )

    transactions_api.get_transactions_by_account.return_value = transactions_response

    result = await mcp_client.call_tool(
        "list_transactions", {"account_id": "acc-checking"}
    )

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["account_id"] == "acc-checking"

    # Verify correct API method was called
    transactions_api.get_transactions_by_account.assert_called_once()
    args = transactions_api.get_transactions_by_account.call_args[0]
    assert args[1] == "acc-checking"  # account_id parameter


async def test_list_transactions_with_amount_filters(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing with amount range filters."""
    # Create transactions with different amounts
    txn_small = ynab.TransactionDetail(
        id="txn-small",
        date=date(2024, 3, 1),
        amount=-25000,  # -$25
        memo="Small purchase",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Coffee Shop",
        category_id="cat-1",
        category_name="Dining Out",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[],
    )

    txn_medium = ynab.TransactionDetail(
        id="txn-medium",
        date=date(2024, 3, 2),
        amount=-60000,  # -$60
        memo="Medium purchase",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Restaurant",
        category_id="cat-1",
        category_name="Dining Out",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[],
    )

    txn_large = ynab.TransactionDetail(
        id="txn-large",
        date=date(2024, 3, 3),
        amount=-120000,  # -$120
        memo="Large purchase",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-3",
        payee_name="Electronics Store",
        category_id="cat-2",
        category_name="Shopping",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[],
    )

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=[txn_small, txn_medium, txn_large], server_knowledge=0
        )
    )

    transactions_api.get_transactions.return_value = transactions_response

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
    transactions_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test transaction listing with split transactions (subtransactions)."""
    sub1 = ynab.SubTransaction(
        id="sub-1",
        transaction_id="txn-split",
        amount=-30000,  # -$30
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
        amount=-20000,  # -$20
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
        amount=-10000,
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
    txn_split = ynab.TransactionDetail(
        id="txn-split",
        date=date(2024, 4, 1),
        amount=-50000,  # -$50 total
        memo="Split transaction at Target",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-target",
        payee_name="Target",
        category_id=None,  # Split transactions don't have a single category
        category_name=None,
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[sub1, sub2, sub_deleted],
    )

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(transactions=[txn_split], server_knowledge=0)
    )

    transactions_api.get_transactions.return_value = transactions_response

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
    transactions_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test transaction listing with pagination."""
    # Create many transactions to test pagination
    transactions = []
    for i in range(5):
        txn = ynab.TransactionDetail(
            id=f"txn-{i}",
            date=date(2024, 1, i + 1),
            amount=-10000 * (i + 1),
            memo=f"Transaction {i}",
            cleared=ynab.TransactionClearedStatus.CLEARED,
            approved=True,
            flag_color=None,
            account_id="acc-1",
            account_name="Checking",
            payee_id=f"payee-{i}",
            payee_name=f"Store {i}",
            category_id="cat-1",
            category_name="Shopping",
            transfer_account_id=None,
            transfer_transaction_id=None,
            matched_transaction_id=None,
            import_id=None,
            import_payee_name=None,
            import_payee_name_original=None,
            debt_transaction_type=None,
            deleted=False,
            subtransactions=[],
        )
        transactions.append(txn)

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=transactions, server_knowledge=0
        )
    )

    transactions_api.get_transactions.return_value = transactions_response

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
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing filtered by category."""

    # Create transaction
    txn = ynab.TransactionDetail(
        id="txn-cat-1",
        date=date(2024, 2, 1),
        amount=-40000,
        memo="Category filtered",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Store",
        category_id="cat-dining",
        category_name="Dining Out",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[],
    )

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(transactions=[txn], server_knowledge=0)
    )

    transactions_api.get_transactions_by_category.return_value = transactions_response

    result = await mcp_client.call_tool(
        "list_transactions", {"category_id": "cat-dining"}
    )

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["category_id"] == "cat-dining"

    # Verify correct API method was called
    transactions_api.get_transactions_by_category.assert_called_once()
    args = transactions_api.get_transactions_by_category.call_args[0]
    assert args[1] == "cat-dining"  # category_id parameter


async def test_list_transactions_with_payee_filter(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction listing filtered by payee."""
    # Create transaction
    txn = ynab.TransactionDetail(
        id="txn-payee-1",
        date=date(2024, 3, 1),
        amount=-80000,
        memo="Payee filtered",
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-amazon",
        payee_name="Amazon",
        category_id="cat-shopping",
        category_name="Shopping",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=False,
        subtransactions=[],
    )

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(transactions=[txn], server_knowledge=0)
    )

    transactions_api.get_transactions_by_payee.return_value = transactions_response

    result = await mcp_client.call_tool(
        "list_transactions", {"payee_id": "payee-amazon"}
    )

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["payee_id"] == "payee-amazon"

    # Verify correct API method was called
    transactions_api.get_transactions_by_payee.assert_called_once()
    args = transactions_api.get_transactions_by_payee.call_args[0]
    assert args[1] == "payee-amazon"  # payee_id parameter
