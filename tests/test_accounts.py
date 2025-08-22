"""
Test account-related MCP tools.
"""

from unittest.mock import MagicMock

import ynab
from assertions import assert_pagination_info, extract_response_data
from conftest import create_ynab_account
from fastmcp.client import Client, FastMCPTransport


async def test_list_accounts_success(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful account listing."""
    open_account = create_ynab_account(
        id="acc-1",
        name="Checking",
        account_type=ynab.AccountType.CHECKING,
        note="Main account",
    )

    closed_account = create_ynab_account(
        id="acc-2",
        name="Savings",
        account_type=ynab.AccountType.SAVINGS,
        closed=True,  # Should be excluded
        balance=0,
    )

    # Mock repository to return test accounts
    mock_repository.get_accounts.return_value = [open_account, closed_account]

    result = await mcp_client.call_tool("list_accounts", {})
    response_data = extract_response_data(result)

    # Should only include open account
    accounts = response_data["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["id"] == "acc-1"
    assert accounts[0]["name"] == "Checking"

    assert_pagination_info(
        response_data["pagination"],
        total_count=1,
        limit=100,
        has_more=False,
    )


async def test_list_accounts_filters_closed_accounts(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test that list_accounts automatically excludes closed accounts."""
    open_checking = create_ynab_account(
        id="acc-1",
        name="Checking",
        account_type=ynab.AccountType.CHECKING,
        closed=False,
    )

    closed_savings = create_ynab_account(
        id="acc-2",
        name="Old Savings",
        account_type=ynab.AccountType.SAVINGS,
        closed=True,
    )

    open_credit = create_ynab_account(
        id="acc-3",
        name="Credit Card",
        account_type=ynab.AccountType.CREDITCARD,
        closed=False,
    )

    mock_repository.get_accounts.return_value = [
        open_checking,
        closed_savings,
        open_credit,
    ]

    result = await mcp_client.call_tool("list_accounts", {})
    response_data = extract_response_data(result)

    # Should only include open accounts
    accounts = response_data["accounts"]
    assert len(accounts) == 2

    account_names = [acc["name"] for acc in accounts]
    assert "Checking" in account_names
    assert "Credit Card" in account_names
    assert "Old Savings" not in account_names  # Closed account excluded


async def test_list_accounts_pagination(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test account listing with pagination."""
    accounts = []
    for i in range(5):
        accounts.append(
            create_ynab_account(
                id=f"acc-{i}",
                name=f"Account {i}",
                closed=False,
            )
        )

    mock_repository.get_accounts.return_value = accounts

    # Test first page
    result = await mcp_client.call_tool("list_accounts", {"limit": 2, "offset": 0})
    response_data = extract_response_data(result)

    assert len(response_data["accounts"]) == 2
    assert_pagination_info(
        response_data["pagination"],
        total_count=5,
        limit=2,
        has_more=True,
    )

    # Test second page
    result = await mcp_client.call_tool("list_accounts", {"limit": 2, "offset": 2})
    response_data = extract_response_data(result)

    assert len(response_data["accounts"]) == 2
    assert_pagination_info(
        response_data["pagination"],
        total_count=5,
        limit=2,
        offset=2,
        has_more=True,
    )


async def test_list_accounts_with_repository_sync(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test that list_accounts triggers repository sync when needed."""
    account = create_ynab_account(id="acc-1", name="Test Account")

    # Mock repository to return empty initially (not initialized)
    mock_repository.get_accounts.return_value = [account]

    result = await mcp_client.call_tool("list_accounts", {})
    response_data = extract_response_data(result)

    # Verify repository was called
    mock_repository.get_accounts.assert_called_once()

    # Verify account data was returned
    assert len(response_data["accounts"]) == 1
    assert response_data["accounts"][0]["id"] == "acc-1"


async def test_list_accounts_account_types(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test that different account types are handled correctly."""
    checking_account = create_ynab_account(
        id="acc-checking",
        name="My Checking",
        account_type=ynab.AccountType.CHECKING,
        on_budget=True,
    )

    savings_account = create_ynab_account(
        id="acc-savings",
        name="Emergency Fund",
        account_type=ynab.AccountType.SAVINGS,
        on_budget=True,
    )

    credit_card = create_ynab_account(
        id="acc-credit",
        name="Visa Card",
        account_type=ynab.AccountType.CREDITCARD,
        on_budget=True,
    )

    investment_account = create_ynab_account(
        id="acc-investment",
        name="401k",
        account_type=ynab.AccountType.OTHERASSET,
        on_budget=False,  # Typically off-budget
    )

    mock_repository.get_accounts.return_value = [
        checking_account,
        savings_account,
        credit_card,
        investment_account,
    ]

    result = await mcp_client.call_tool("list_accounts", {})
    response_data = extract_response_data(result)

    # All account types should be included (none are closed)
    accounts = response_data["accounts"]
    assert len(accounts) == 4

    # Verify account types are preserved
    account_types = {acc["id"]: acc["type"] for acc in accounts}
    assert account_types["acc-checking"] == "checking"
    assert account_types["acc-savings"] == "savings"
    assert account_types["acc-credit"] == "creditCard"
    assert account_types["acc-investment"] == "otherAsset"

    # Verify on_budget status
    on_budget_status = {acc["id"]: acc["on_budget"] for acc in accounts}
    assert on_budget_status["acc-checking"] is True
    assert on_budget_status["acc-investment"] is False
