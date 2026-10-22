"""
Test the tool that describes the plan itself.
"""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
import ynab
from assertions import extract_response_data
from fastmcp.client import Client, FastMCPTransport
from ids import uid


@pytest.fixture
def plan_settings(plans_api: MagicMock) -> None:
    plans_api.get_plan_settings_by_id.return_value = ynab.PlanSettingsResponse(
        data=ynab.PlanSettingsResponseData(
            settings=ynab.PlanSettings(
                date_format=ynab.DateFormat(format="MM/DD/YYYY"),
                currency_format=ynab.CurrencyFormat(
                    iso_code="USD",
                    example_format="123,456.78",
                    decimal_digits=2,
                    decimal_separator=".",
                    symbol_first=True,
                    group_separator=",",
                    currency_symbol="$",
                    display_symbol=True,
                ),
            )
        )
    )


def create_ynab_plan_summary(*, name: str) -> ynab.PlanSummary:
    """Create a YNAB plan summary for testing with sensible defaults."""
    return ynab.PlanSummary(
        id=uid(f"plan-{name}"),
        name=name,
        last_modified_on=datetime(2024, 3, 15, 9, 0, tzinfo=UTC),
        first_month=date(2022, 1, 1),
        last_month=date(2024, 4, 1),
    )


def plan_summaries(*plans: ynab.PlanSummary) -> ynab.PlanSummaryResponse:
    """Wrap plan summaries the way YNAB answers a list of plans."""
    return ynab.PlanSummaryResponse(
        data=ynab.PlanSummaryResponseData(plans=list(plans))
    )


@pytest.mark.usefixtures("plan_settings")
async def test_get_plan(
    mock_repository: MagicMock,
    plans_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    mock_repository.plan_id = str(uid("plan-Household"))
    plans_api.get_plans.return_value = plan_summaries(
        create_ynab_plan_summary(name="Side Business"),
        create_ynab_plan_summary(name="Household"),
    )

    result = await mcp_client.call_tool("get_plan", {})

    assert extract_response_data(result) == {
        "id": str(uid("plan-Household")),
        "name": "Household",
        "first_month": "2022-01-01",
        "last_month": "2024-04-01",
        "last_modified_on": "2024-03-15T09:00:00Z",
        "currency_format": {
            "iso_code": "USD",
            "example_format": "123,456.78",
            "decimal_digits": 2,
            "currency_symbol": "$",
            "symbol_first": True,
        },
        "date_format": "MM/DD/YYYY",
    }
    assert plans_api.get_plan_settings_by_id.call_args.args == (
        str(uid("plan-Household")),
    )


@pytest.mark.usefixtures("plan_settings")
async def test_get_plan_has_no_name_when_the_plan_is_not_listed(
    plans_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    plans_api.get_plans.return_value = plan_summaries(
        create_ynab_plan_summary(name="Side Business")
    )

    result = await mcp_client.call_tool("get_plan", {})

    assert extract_response_data(result) == {
        "id": "test_plan_id",
        "name": None,
        "first_month": None,
        "last_month": None,
        "last_modified_on": None,
        "currency_format": {
            "iso_code": "USD",
            "example_format": "123,456.78",
            "decimal_digits": 2,
            "currency_symbol": "$",
            "symbol_first": True,
        },
        "date_format": "MM/DD/YYYY",
    }
