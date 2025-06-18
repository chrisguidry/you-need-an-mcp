"""
Test budget-related MCP tools.
"""

import json
from unittest.mock import MagicMock

import ynab
from fastmcp.client import Client, FastMCPTransport
from mcp.types import TextContent


async def test_list_budgets_success(
    budgets_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test successful budget listing."""
    currency_format = ynab.CurrencyFormat(
        iso_code="USD",
        example_format="$123.45",
        decimal_digits=2,
        decimal_separator=".",
        symbol_first=True,
        group_separator=",",
        currency_symbol="$",
        display_symbol=True,
    )

    test_budget = ynab.BudgetSummary(
        id="budget-123",
        name="Test Budget",
        last_modified_on=None,
        first_month=None,
        last_month=None,
        date_format=None,
        currency_format=currency_format,
        accounts=None,
    )

    budgets_response = ynab.BudgetSummaryResponse(
        data=ynab.BudgetSummaryResponseData(budgets=[test_budget])
    )
    budgets_api.get_budgets.return_value = budgets_response

    result = await mcp_client.call_tool("list_budgets", {})

    assert len(result) == 1
    # The result is a list of Budget objects serialized as JSON
    budgets_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert budgets_data is not None
    # budgets_data is a single Budget object, not a list
    assert budgets_data["id"] == "budget-123"
    assert budgets_data["name"] == "Test Budget"
    assert budgets_data["currency_format"]["iso_code"] == "USD"


async def test_list_budgets_null_currency(
    budgets_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test budget listing with null currency format."""
    test_budget = ynab.BudgetSummary(
        id="budget-456",
        name="Budget No Currency",
        last_modified_on=None,
        first_month=None,
        last_month=None,
        date_format=None,
        currency_format=None,
        accounts=None,
    )

    budgets_response = ynab.BudgetSummaryResponse(
        data=ynab.BudgetSummaryResponseData(budgets=[test_budget])
    )
    budgets_api.get_budgets.return_value = budgets_response

    result = await mcp_client.call_tool("list_budgets", {})

    assert len(result) == 1
    budgets_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert budgets_data is not None
    assert budgets_data["id"] == "budget-456"
    assert budgets_data["currency_format"] is None
