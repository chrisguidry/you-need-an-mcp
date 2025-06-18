"""
Test account-related MCP tools.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import ynab
from fastmcp.client import Client, FastMCPTransport
from mcp.types import TextContent


async def test_list_accounts_success(
    mock_environment_variables: None,
    accounts_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful account listing."""
    open_account = ynab.Account(
        id="acc-1",
        name="Checking",
        type=ynab.AccountType.CHECKING,
        on_budget=True,
        closed=False,
        note="Main account",
        balance=100000,  # $100.00
        cleared_balance=95000,
        uncleared_balance=5000,
        transfer_payee_id="payee-1",
        direct_import_linked=True,
        direct_import_in_error=False,
        last_reconciled_at=datetime(2024, 1, 10, 9, 0, 0),
        debt_original_balance=None,
        debt_interest_rates=None,
        debt_minimum_payments=None,
        debt_escrow_amounts=None,
        deleted=False,
    )

    closed_account = ynab.Account(
        id="acc-2",
        name="Savings",
        type=ynab.AccountType.SAVINGS,
        on_budget=False,
        closed=True,  # Closed account - should be excluded
        note=None,
        balance=0,
        cleared_balance=0,
        uncleared_balance=0,
        transfer_payee_id=None,
        direct_import_linked=False,
        direct_import_in_error=False,
        last_reconciled_at=None,
        debt_original_balance=None,
        debt_interest_rates=None,
        debt_minimum_payments=None,
        debt_escrow_amounts=None,
        deleted=False,
    )

    accounts_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[open_account, closed_account], server_knowledge=0
        )
    )
    accounts_api.get_accounts.return_value = accounts_response

    result = await mcp_client.call_tool("list_accounts", {})

    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None
    # Should only include open account
    assert len(response_data["accounts"]) == 1
    assert response_data["accounts"][0]["id"] == "acc-1"
    assert response_data["accounts"][0]["name"] == "Checking"
