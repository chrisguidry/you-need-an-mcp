"""
Tests for scheduled transaction functionality in YNAB MCP Server.

Tests the list_scheduled_transactions tool with various filters and scenarios.
"""

import json
from datetime import date
from unittest.mock import MagicMock

import ynab
from fastmcp.client import Client, FastMCPTransport
from mcp.types import TextContent


async def test_list_scheduled_transactions_basic(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test basic scheduled transaction listing without filters."""

    st1 = ynab.ScheduledTransactionDetail(
        id="st-1",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-120000,  # -$120.00 outflow
        memo="Netflix subscription",
        flag_color=ynab.TransactionFlagColor.RED,
        flag_name="Entertainment",
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Netflix",
        category_id="cat-1",
        category_name="Entertainment",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st2 = ynab.ScheduledTransactionDetail(
        id="st-2",
        date_first=date(2024, 1, 15),
        date_next=date(2024, 1, 29),
        frequency="weekly",
        amount=-5000,  # -$5.00 outflow
        memo="Weekly coffee",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Coffee Shop",
        category_id="cat-2",
        category_name="Dining Out",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    # Add a deleted scheduled transaction that should be filtered out
    st_deleted = ynab.ScheduledTransactionDetail(
        id="st-deleted",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 3, 1),
        frequency="monthly",
        amount=-50000,
        memo="Deleted subscription",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-3",
        payee_name="Old Service",
        category_id="cat-1",
        category_name="Entertainment",
        transfer_account_id=None,
        deleted=True,  # Should be excluded
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[
                st2,
                st1,
                st_deleted,
            ],  # Out of order to test sorting
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    result = await mcp_client.call_tool("list_scheduled_transactions", {})

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should have 2 scheduled transactions (deleted one excluded)
    assert len(response_data["scheduled_transactions"]) == 2

    # Should be sorted by next date ascending (earliest scheduled first)
    assert response_data["scheduled_transactions"][0]["id"] == "st-2"
    assert response_data["scheduled_transactions"][0]["date_next"] == "2024-01-29"
    assert response_data["scheduled_transactions"][0]["frequency"] == "weekly"
    assert response_data["scheduled_transactions"][0]["amount"] == "-5"
    assert response_data["scheduled_transactions"][0]["payee_name"] == "Coffee Shop"

    assert response_data["scheduled_transactions"][1]["id"] == "st-1"
    assert response_data["scheduled_transactions"][1]["date_next"] == "2024-02-01"
    assert response_data["scheduled_transactions"][1]["frequency"] == "monthly"
    assert response_data["scheduled_transactions"][1]["amount"] == "-120"
    assert response_data["scheduled_transactions"][1]["flag_color"] == "red"
    assert response_data["scheduled_transactions"][1]["flag_name"] == "Entertainment"

    # Check pagination
    assert response_data["pagination"]["total_count"] == 2
    assert response_data["pagination"]["has_more"] is False
    assert response_data["pagination"]["returned_count"] == 2


async def test_list_scheduled_transactions_with_frequency_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by frequency."""

    st_monthly = ynab.ScheduledTransactionDetail(
        id="st-monthly",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-100000,
        memo="Monthly bill",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Electric Company",
        category_id="cat-1",
        category_name="Utilities",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st_weekly = ynab.ScheduledTransactionDetail(
        id="st-weekly",
        date_first=date(2024, 1, 8),
        date_next=date(2024, 1, 15),
        frequency="weekly",
        amount=-2500,
        memo="Weekly groceries",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Grocery Store",
        category_id="cat-2",
        category_name="Groceries",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_monthly, st_weekly],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test filtering by monthly frequency
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"frequency": "monthly"}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should only have the monthly scheduled transaction
    assert len(response_data["scheduled_transactions"]) == 1
    assert response_data["scheduled_transactions"][0]["id"] == "st-monthly"
    assert response_data["scheduled_transactions"][0]["frequency"] == "monthly"
    assert (
        response_data["scheduled_transactions"][0]["payee_name"] == "Electric Company"
    )

    # Check pagination
    assert response_data["pagination"]["total_count"] == 1
    assert response_data["pagination"]["has_more"] is False


async def test_list_scheduled_transactions_with_upcoming_days_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by upcoming days."""

    # Scheduled for 5 days from now
    st_soon = ynab.ScheduledTransactionDetail(
        id="st-soon",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 1, 20),  # 5 days from "today" (2024-01-15)
        frequency="monthly",
        amount=-50000,
        memo="Due soon",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Due Soon Co",
        category_id="cat-1",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    # Scheduled for 15 days from now
    st_later = ynab.ScheduledTransactionDetail(
        id="st-later",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 1, 30),  # 15 days from "today" (2024-01-15)
        frequency="monthly",
        amount=-75000,
        memo="Due later",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Due Later Co",
        category_id="cat-1",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_soon, st_later],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Mock datetime.now() to return a fixed date for testing
    from unittest.mock import patch

    import server

    with patch.object(server, "datetime") as mock_datetime:
        mock_datetime.now.return_value.date.return_value = date(2024, 1, 15)

        # Test filtering by upcoming 7 days
        result = await mcp_client.call_tool(
            "list_scheduled_transactions", {"upcoming_days": 7}
        )

        assert len(result) == 1
        response_data = (
            json.loads(result[0].text) if isinstance(result[0], TextContent) else None
        )
        assert response_data is not None

        # Should only have the transaction due within 7 days
        assert len(response_data["scheduled_transactions"]) == 1
        assert response_data["scheduled_transactions"][0]["id"] == "st-soon"
        assert response_data["scheduled_transactions"][0]["payee_name"] == "Due Soon Co"


async def test_list_scheduled_transactions_with_amount_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by amount range."""

    st_small = ynab.ScheduledTransactionDetail(
        id="st-small",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-1000,  # -$1.00
        memo="Small expense",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Small Store",
        category_id="cat-1",
        category_name="Misc",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st_large = ynab.ScheduledTransactionDetail(
        id="st-large",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-500000,  # -$500.00
        memo="Large expense",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Large Store",
        category_id="cat-1",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_small, st_large],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test filtering by minimum amount (expenses <= -$10, i.e., larger expenses)
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"max_amount": -10}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should only have the large transaction (<= -$10)
    assert len(response_data["scheduled_transactions"]) == 1
    assert response_data["scheduled_transactions"][0]["id"] == "st-large"
    assert response_data["scheduled_transactions"][0]["amount"] == "-500"


async def test_list_scheduled_transactions_with_account_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by account."""

    st_checking = ynab.ScheduledTransactionDetail(
        id="st-checking",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-100000,
        memo="Checking account expense",
        flag_color=None,
        flag_name=None,
        account_id="acc-checking",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Merchant A",
        category_id="cat-1",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st_savings = ynab.ScheduledTransactionDetail(
        id="st-savings",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-50000,
        memo="Savings account expense",
        flag_color=None,
        flag_name=None,
        account_id="acc-savings",
        account_name="Savings",
        payee_id="payee-2",
        payee_name="Merchant B",
        category_id="cat-1",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_checking, st_savings],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test filtering by checking account
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"account_id": "acc-checking"}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should only have the checking account scheduled transaction
    assert len(response_data["scheduled_transactions"]) == 1
    assert response_data["scheduled_transactions"][0]["id"] == "st-checking"
    assert response_data["scheduled_transactions"][0]["account_name"] == "Checking"


async def test_list_scheduled_transactions_with_category_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by category."""

    st_bills = ynab.ScheduledTransactionDetail(
        id="st-bills",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-100000,
        memo="Monthly bill",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Utility Co",
        category_id="cat-bills",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st_entertainment = ynab.ScheduledTransactionDetail(
        id="st-entertainment",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-1500,
        memo="Entertainment subscription",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Streaming Service",
        category_id="cat-entertainment",
        category_name="Entertainment",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_bills, st_entertainment],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test filtering by bills category
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"category_id": "cat-bills"}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should only have the bills category scheduled transaction
    assert len(response_data["scheduled_transactions"]) == 1
    assert response_data["scheduled_transactions"][0]["id"] == "st-bills"
    assert response_data["scheduled_transactions"][0]["category_name"] == "Bills"


async def test_list_scheduled_transactions_with_min_amount_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by minimum amount."""

    st_small = ynab.ScheduledTransactionDetail(
        id="st-small",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-1000,  # -$1.00
        memo="Small expense",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Small Store",
        category_id="cat-1",
        category_name="Misc",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st_large = ynab.ScheduledTransactionDetail(
        id="st-large",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-500000,  # -$500.00
        memo="Large expense",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-2",
        payee_name="Large Store",
        category_id="cat-1",
        category_name="Bills",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_small, st_large],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test filtering by minimum amount (only expenses >= -$5, excludes -$500)
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"min_amount": -5}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should only have the small transaction (>= -$5)
    assert len(response_data["scheduled_transactions"]) == 1
    assert response_data["scheduled_transactions"][0]["id"] == "st-small"
    assert response_data["scheduled_transactions"][0]["amount"] == "-1"


async def test_list_scheduled_transactions_with_payee_filter(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing filtered by payee."""

    st_netflix = ynab.ScheduledTransactionDetail(
        id="st-netflix",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-1500,
        memo="Netflix subscription",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-netflix",
        payee_name="Netflix",
        category_id="cat-1",
        category_name="Entertainment",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    st_spotify = ynab.ScheduledTransactionDetail(
        id="st-spotify",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-1000,
        memo="Spotify subscription",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-spotify",
        payee_name="Spotify",
        category_id="cat-1",
        category_name="Entertainment",
        transfer_account_id=None,
        deleted=False,
        subtransactions=[],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_netflix, st_spotify],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test filtering by Netflix payee
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"payee_id": "payee-netflix"}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should only have the Netflix scheduled transaction
    assert len(response_data["scheduled_transactions"]) == 1
    assert response_data["scheduled_transactions"][0]["id"] == "st-netflix"
    assert response_data["scheduled_transactions"][0]["payee_name"] == "Netflix"


async def test_list_scheduled_transactions_pagination(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing with pagination."""

    # Create multiple scheduled transactions
    scheduled_transactions = []
    for i in range(15):
        st = ynab.ScheduledTransactionDetail(
            id=f"st-{i}",
            date_first=date(2024, 1, 1),
            date_next=date(2024, 2, i + 1),  # Different next dates for sorting
            frequency="monthly",
            amount=-10000 * (i + 1),
            memo=f"Transaction {i}",
            flag_color=None,
            flag_name=None,
            account_id="acc-1",
            account_name="Checking",
            payee_id=f"payee-{i}",
            payee_name=f"Payee {i}",
            category_id="cat-1",
            category_name="Bills",
            transfer_account_id=None,
            deleted=False,
            subtransactions=[],
        )
        scheduled_transactions.append(st)

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=scheduled_transactions,
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    # Test first page with limit
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"limit": 5, "offset": 0}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should have 5 scheduled transactions
    assert len(response_data["scheduled_transactions"]) == 5
    assert response_data["pagination"]["total_count"] == 15
    assert response_data["pagination"]["has_more"] is True
    assert response_data["pagination"]["next_offset"] == 5
    assert response_data["pagination"]["returned_count"] == 5

    # Test second page
    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"limit": 5, "offset": 5}
    )

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should have next 5 scheduled transactions
    assert len(response_data["scheduled_transactions"]) == 5
    assert response_data["pagination"]["total_count"] == 15
    assert response_data["pagination"]["has_more"] is True
    assert response_data["pagination"]["next_offset"] == 10


async def test_list_scheduled_transactions_with_subtransactions(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing with split transactions (subtransactions)."""

    # Create scheduled subtransactions
    sub1 = ynab.ScheduledSubTransaction(
        id="sub-1",
        scheduled_transaction_id="st-split",
        amount=-30000,  # -$30.00 for groceries
        memo="Groceries portion",
        payee_id="payee-1",
        payee_name="Grocery Store",
        category_id="cat-groceries",
        category_name="Groceries",
        transfer_account_id=None,
        deleted=False,
    )

    sub2 = ynab.ScheduledSubTransaction(
        id="sub-2",
        scheduled_transaction_id="st-split",
        amount=-20000,  # -$20.00 for household
        memo="Household portion",
        payee_id="payee-1",
        payee_name="Grocery Store",
        category_id="cat-household",
        category_name="Household",
        transfer_account_id=None,
        deleted=False,
    )

    st_split = ynab.ScheduledTransactionDetail(
        id="st-split",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-50000,  # -$50.00 total (should equal sum of subtransactions)
        memo="Split transaction",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Grocery Store",
        category_id=None,  # Split transactions don't have a main category
        category_name=None,
        transfer_account_id=None,
        deleted=False,
        subtransactions=[sub1, sub2],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_split],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    result = await mcp_client.call_tool("list_scheduled_transactions", {})

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should have 1 scheduled transaction with subtransactions
    assert len(response_data["scheduled_transactions"]) == 1
    st = response_data["scheduled_transactions"][0]

    assert st["id"] == "st-split"
    assert st["amount"] == "-50"
    assert st["memo"] == "Split transaction"

    # Check subtransactions
    assert len(st["subtransactions"]) == 2

    assert st["subtransactions"][0]["id"] == "sub-1"
    assert st["subtransactions"][0]["amount"] == "-30"
    assert st["subtransactions"][0]["category_name"] == "Groceries"

    assert st["subtransactions"][1]["id"] == "sub-2"
    assert st["subtransactions"][1]["amount"] == "-20"
    assert st["subtransactions"][1]["category_name"] == "Household"


async def test_list_scheduled_transactions_with_deleted_subtransactions(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test scheduled transaction listing excludes deleted subtransactions."""

    # Create active and deleted scheduled subtransactions
    sub_active = ynab.ScheduledSubTransaction(
        id="sub-active",
        scheduled_transaction_id="st-mixed",
        amount=-30000,  # -$30.00
        memo="Active subtransaction",
        payee_id="payee-1",
        payee_name="Store",
        category_id="cat-1",
        category_name="Active Category",
        transfer_account_id=None,
        deleted=False,
    )

    sub_deleted = ynab.ScheduledSubTransaction(
        id="sub-deleted",
        scheduled_transaction_id="st-mixed",
        amount=-20000,  # -$20.00
        memo="Deleted subtransaction",
        payee_id="payee-1",
        payee_name="Store",
        category_id="cat-2",
        category_name="Deleted Category",
        transfer_account_id=None,
        deleted=True,  # Should be excluded
    )

    st_mixed = ynab.ScheduledTransactionDetail(
        id="st-mixed",
        date_first=date(2024, 1, 1),
        date_next=date(2024, 2, 1),
        frequency="monthly",
        amount=-50000,  # -$50.00 total
        memo="Mixed subtransactions",
        flag_color=None,
        flag_name=None,
        account_id="acc-1",
        account_name="Checking",
        payee_id="payee-1",
        payee_name="Store",
        category_id=None,
        category_name=None,
        transfer_account_id=None,
        deleted=False,
        subtransactions=[sub_active, sub_deleted],
    )

    scheduled_transactions_response = ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=[st_mixed],
            server_knowledge=0,
        )
    )

    scheduled_transactions_api.get_scheduled_transactions.return_value = (
        scheduled_transactions_response
    )

    result = await mcp_client.call_tool("list_scheduled_transactions", {})

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None

    # Should have 1 scheduled transaction with only active subtransactions
    assert len(response_data["scheduled_transactions"]) == 1
    st = response_data["scheduled_transactions"][0]

    assert st["id"] == "st-mixed"
    assert st["amount"] == "-50"

    # Should only have the active subtransaction (deleted one excluded)
    assert len(st["subtransactions"]) == 1
    assert st["subtransactions"][0]["id"] == "sub-active"
    assert st["subtransactions"][0]["deleted"] is False
    assert st["subtransactions"][0]["category_name"] == "Active Category"
