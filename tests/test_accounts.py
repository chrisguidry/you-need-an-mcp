"""
Test account-related MCP tools.
"""

from typing import Any
from unittest.mock import MagicMock

import ynab
from assertions import assert_pagination_info, extract_response_data
from fastmcp.client import Client, FastMCPTransport


def create_ynab_account(
    *,
    id: str = "acc-1",
    name: str = "Test Account",
    account_type: ynab.AccountType = ynab.AccountType.CHECKING,
    on_budget: bool = True,
    closed: bool = False,
    balance: int = 100_000,  # $100.00
    **kwargs: Any,
) -> ynab.Account:
    """Create a YNAB Account for testing with sensible defaults."""
    return ynab.Account(
        id=id,
        name=name,
        type=account_type,
        on_budget=on_budget,
        closed=closed,
        note=kwargs.get("note"),
        balance=balance,
        cleared_balance=kwargs.get("cleared_balance", balance - 5_000),
        uncleared_balance=kwargs.get("uncleared_balance", 5_000),
        transfer_payee_id=kwargs.get("transfer_payee_id"),
        direct_import_linked=kwargs.get("direct_import_linked", False),
        direct_import_in_error=kwargs.get("direct_import_in_error", False),
        last_reconciled_at=kwargs.get("last_reconciled_at"),
        debt_original_balance=kwargs.get("debt_original_balance"),
        debt_interest_rates=kwargs.get("debt_interest_rates"),
        debt_minimum_payments=kwargs.get("debt_minimum_payments"),
        debt_escrow_amounts=kwargs.get("debt_escrow_amounts"),
        deleted=kwargs.get("deleted", False),
    )


async def test_list_accounts_success(
    mock_environment_variables: None,
    accounts_api: MagicMock,
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

    accounts_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[open_account, closed_account], server_knowledge=0
        )
    )
    accounts_api.get_accounts.return_value = accounts_response

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
