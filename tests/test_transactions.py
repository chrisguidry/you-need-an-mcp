"""
Tests for transaction-related functionality in YNAB MCP Server.

Tests the list_transactions tool with various filters and scenarios.
"""

import json
from datetime import date
from unittest.mock import MagicMock

import ynab
from fastmcp import Client


async def test_list_transactions_basic(transactions_api: MagicMock, mcp_client: Client):
    """Test basic transaction listing without filters."""

    txn1 = ynab.TransactionDetail(
        id="txn-1",
        var_date=date(2024, 1, 15),
        amount=-50000,  # -$50.00 outflow
        memo="Grocery shopping",
        cleared="cleared",
        approved=True,
        flag_color="red",
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Whole Foods",
        category_id="cat-1",
        category_name="Groceries",
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

    txn2 = ynab.TransactionDetail(
        id="txn-2",
        var_date=date(2024, 1, 20),
        amount=-75000,  # -$75.00 outflow
        memo="Dinner",
        cleared="uncleared",
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Restaurant XYZ",
        category_id="cat-2",
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

    # Add a deleted transaction that should be filtered out
    txn_deleted = ynab.TransactionDetail(
        id="txn-deleted",
        var_date=date(2024, 1, 10),
        amount=-25000,
        memo="Deleted transaction",
        cleared="cleared",
        approved=True,
        flag_color=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-3",
        payee_name="Store ABC",
        category_id="cat-1",
        category_name="Groceries",
        transfer_account_id=None,
        transfer_transaction_id=None,
        matched_transaction_id=None,
        import_id=None,
        import_payee_name=None,
        import_payee_name_original=None,
        debt_transaction_type=None,
        deleted=True,  # Should be excluded
        subtransactions=[],
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
    response_data = json.loads(result[0].text)

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
    assert response_data["transactions"][1]["flag_color"] == "red"

    # Check pagination
    assert response_data["pagination"]["total_count"] == 2
    assert response_data["pagination"]["has_more"] is False
    assert response_data["pagination"]["returned_count"] == 2


async def test_list_transactions_with_account_filter(
    transactions_api: MagicMock,
    mcp_client: Client,
) -> None:
    """Test transaction listing filtered by account."""
    # Create transaction
    txn = ynab.TransactionDetail(
        id="txn-acc-1",
        var_date=date(2024, 2, 1),
        amount=-30000,
        memo="Account filtered",
        cleared="cleared",
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
    response_data = json.loads(result[0].text)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["account_id"] == "acc-checking"

    # Verify correct API method was called
    transactions_api.get_transactions_by_account.assert_called_once()
    args = transactions_api.get_transactions_by_account.call_args[0]
    assert args[1] == "acc-checking"  # account_id parameter


async def test_list_transactions_with_amount_filters(
    transactions_api: MagicMock,
    mcp_client: Client,
) -> None:
    """Test transaction listing with amount range filters."""
    # Create transactions with different amounts
    txn_small = ynab.TransactionDetail(
        id="txn-small",
        var_date=date(2024, 3, 1),
        amount=-25000,  # -$25
        memo="Small purchase",
        cleared="cleared",
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
        var_date=date(2024, 3, 2),
        amount=-60000,  # -$60
        memo="Medium purchase",
        cleared="cleared",
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
        var_date=date(2024, 3, 3),
        amount=-120000,  # -$120
        memo="Large purchase",
        cleared="cleared",
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

    response_data = json.loads(result[0].text)
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

    response_data = json.loads(result[0].text)
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

    response_data = json.loads(result[0].text)
    # Should only include medium transaction (-$60)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["id"] == "txn-medium"


async def test_list_transactions_with_subtransactions(
    transactions_api: MagicMock, mcp_client: Client
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
        var_date=date(2024, 4, 1),
        amount=-50000,  # -$50 total
        memo="Split transaction at Target",
        cleared="cleared",
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

    response_data = json.loads(result[0].text)
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
    transactions_api: MagicMock, mcp_client: Client
):
    """Test transaction listing with pagination."""
    # Create many transactions to test pagination
    transactions = []
    for i in range(5):
        txn = ynab.TransactionDetail(
            id=f"txn-{i}",
            var_date=date(2024, 1, i + 1),
            amount=-10000 * (i + 1),
            memo=f"Transaction {i}",
            cleared="cleared",
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

    response_data = json.loads(result[0].text)
    assert len(response_data["transactions"]) == 2
    assert response_data["pagination"]["total_count"] == 5
    assert response_data["pagination"]["has_more"] is True
    assert response_data["pagination"]["next_offset"] == 2
    assert response_data["pagination"]["returned_count"] == 2

    # Transactions should be sorted by date descending
    assert response_data["transactions"][0]["id"] == "txn-4"
    assert response_data["transactions"][1]["id"] == "txn-3"

    # Test second page
    result = await mcp_client.call_tool("list_transactions", {"limit": 2, "offset": 2})

    response_data = json.loads(result[0].text)
    assert len(response_data["transactions"]) == 2
    assert response_data["transactions"][0]["id"] == "txn-2"
    assert response_data["transactions"][1]["id"] == "txn-1"


async def test_list_transactions_with_category_filter(
    transactions_api: MagicMock,
    mcp_client: Client,
) -> None:
    """Test transaction listing filtered by category."""

    # Create transaction
    txn = ynab.TransactionDetail(
        id="txn-cat-1",
        var_date=date(2024, 2, 1),
        amount=-40000,
        memo="Category filtered",
        cleared="cleared",
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
    response_data = json.loads(result[0].text)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["category_id"] == "cat-dining"

    # Verify correct API method was called
    transactions_api.get_transactions_by_category.assert_called_once()
    args = transactions_api.get_transactions_by_category.call_args[0]
    assert args[1] == "cat-dining"  # category_id parameter


async def test_list_transactions_with_payee_filter(
    transactions_api: MagicMock,
    mcp_client: Client,
) -> None:
    """Test transaction listing filtered by payee."""
    # Create transaction
    txn = ynab.TransactionDetail(
        id="txn-payee-1",
        var_date=date(2024, 3, 1),
        amount=-80000,
        memo="Payee filtered",
        cleared="cleared",
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
    response_data = json.loads(result[0].text)
    assert len(response_data["transactions"]) == 1
    assert response_data["transactions"][0]["payee_id"] == "payee-amazon"

    # Verify correct API method was called
    transactions_api.get_transactions_by_payee.assert_called_once()
    args = transactions_api.get_transactions_by_payee.call_args[0]
    assert args[1] == "payee-amazon"  # payee_id parameter
