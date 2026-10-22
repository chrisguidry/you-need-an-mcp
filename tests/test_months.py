"""
Test the plan month tools and how a month argument names a month.
"""

from datetime import date
from typing import cast
from unittest.mock import MagicMock

import pytest
import ynab
from assertions import assert_pagination_info, extract_response_data
from conftest import create_ynab_category, create_ynab_category_group
from fastmcp.client import Client, FastMCPTransport
from ids import uid

from months import Month, resolve_month


@pytest.mark.parametrize(
    ("month", "today", "first_of_month"),
    [
        ("current", date(2024, 6, 15), date(2024, 6, 1)),
        ("last", date(2024, 6, 15), date(2024, 5, 1)),
        ("next", date(2024, 6, 15), date(2024, 7, 1)),
        ("last", date(2024, 1, 31), date(2023, 12, 1)),
        ("next", date(2024, 1, 31), date(2024, 2, 1)),
        ("last", date(2024, 12, 1), date(2024, 11, 1)),
        ("next", date(2024, 12, 31), date(2025, 1, 1)),
        (date(2024, 3, 17), date(2024, 6, 15), date(2024, 3, 1)),
        (date(2024, 3, 1), date(2024, 6, 15), date(2024, 3, 1)),
    ],
)
def test_resolve_month(month: Month, today: date, first_of_month: date) -> None:
    assert resolve_month(month, today) == first_of_month


def test_resolve_month_defaults_to_today() -> None:
    assert resolve_month("current") == date.today().replace(day=1)


def test_resolve_month_rejects_an_unknown_month() -> None:
    with pytest.raises(ValueError, match="Invalid month value: someday"):
        resolve_month(cast(Month, "someday"))


def create_ynab_month_detail(
    *,
    month: date = date(2024, 1, 1),
    categories: list[ynab.Category] | None = None,
    income: int = 0,
    budgeted: int = 0,
    activity: int = 0,
    to_be_budgeted: int = 0,
    note: str | None = None,
    age_of_money: int | None = None,
) -> ynab.MonthDetailResponse:
    """Create YNAB's answer for one plan month, with sensible defaults."""
    return ynab.MonthDetailResponse(
        data=ynab.MonthDetailResponseData(
            month=ynab.MonthDetail(
                month=month,
                note=note,
                income=income,
                budgeted=budgeted,
                activity=activity,
                to_be_budgeted=to_be_budgeted,
                age_of_money=age_of_money,
                deleted=False,
                categories=categories or [],
            )
        )
    )


async def test_get_plan_month_reports_the_month_totals(
    mock_repository: MagicMock,
    months_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    months_api.get_plan_month.return_value = create_ynab_month_detail(
        month=date(2024, 1, 1),
        note="Tight month",
        income=4_000_000,
        budgeted=3_500_250,
        activity=-2_000_000,
        to_be_budgeted=-12_500,
        age_of_money=15,
    )
    mock_repository.get_category_groups.return_value = []

    result = await mcp_client.call_tool("get_plan_month", {"month": "2024-01-20"})

    assert extract_response_data(result) == {
        "month": "2024-01-01",
        "note": "Tight month",
        "income": "4000",
        "assigned": "3500.25",
        "activity": "-2000",
        "ready_to_assign": "-12.5",
        "age_of_money": 15,
        "categories": [],
        "pagination": {"total_count": 0, "limit": 50, "offset": 0, "has_more": False},
    }
    assert months_api.get_plan_month.call_args.args == (
        "test_plan_id",
        date(2024, 1, 1),
    )


async def test_get_plan_month_asks_for_the_current_month_by_default(
    mock_repository: MagicMock,
    months_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    months_api.get_plan_month.return_value = create_ynab_month_detail()
    mock_repository.get_category_groups.return_value = []

    await mcp_client.call_tool("get_plan_month", {})

    assert months_api.get_plan_month.call_args.args == (
        "test_plan_id",
        resolve_month("current"),
    )


async def test_get_plan_month_lists_visible_categories_with_their_group_names(
    mock_repository: MagicMock,
    months_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    groceries = create_ynab_category(id=uid("cat-groceries"), name="Groceries")
    rent = create_ynab_category(id=uid("cat-rent"), name="Rent")
    months_api.get_plan_month.return_value = create_ynab_month_detail(
        categories=[
            groceries,
            rent,
            create_ynab_category(id=uid("cat-hidden"), name="Hidden", hidden=True),
            create_ynab_category(id=uid("cat-gone"), name="Gone", deleted=True),
        ]
    )
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(name="Everyday", categories=[groceries])
    ]

    result = await mcp_client.call_tool("get_plan_month", {"month": "2024-01-01"})

    categories = extract_response_data(result)["categories"]
    assert [
        (category["name"], category["category_group_name"]) for category in categories
    ] == [("Groceries", "Everyday"), ("Rent", None)]


async def test_get_plan_month_pages_through_categories(
    mock_repository: MagicMock,
    months_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    months_api.get_plan_month.return_value = create_ynab_month_detail(
        categories=[
            create_ynab_category(id=uid(f"cat-{index}"), name=f"Category {index}")
            for index in range(3)
        ]
    )
    mock_repository.get_category_groups.return_value = []

    result = await mcp_client.call_tool(
        "get_plan_month", {"month": "2024-01-01", "limit": 1, "offset": 1}
    )

    plan_month = extract_response_data(result)
    assert [category["name"] for category in plan_month["categories"]] == ["Category 1"]
    assert_pagination_info(
        plan_month["pagination"], total_count=3, limit=1, offset=1, has_more=True
    )


def create_ynab_month_summary(
    month: date, *, budgeted: int = 0, deleted: bool = False
) -> ynab.MonthSummary:
    """Create a YNAB month summary for testing with sensible defaults."""
    return ynab.MonthSummary(
        month=month,
        income=0,
        budgeted=budgeted,
        activity=0,
        to_be_budgeted=0,
        deleted=deleted,
    )


def month_summaries(*months: ynab.MonthSummary) -> ynab.MonthSummariesResponse:
    """Wrap month summaries the way YNAB answers a list of months."""
    return ynab.MonthSummariesResponse(
        data=ynab.MonthSummariesResponseData(months=list(months), server_knowledge=1)
    )


async def test_list_plan_months_lists_newest_first(
    months_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    months_api.get_plan_months.return_value = month_summaries(
        create_ynab_month_summary(date(2024, 1, 1), budgeted=1_000_000),
        create_ynab_month_summary(date(2024, 3, 1), budgeted=3_000_000),
        create_ynab_month_summary(date(2024, 2, 1), budgeted=2_000_000),
    )

    result = await mcp_client.call_tool("list_plan_months", {})

    months = extract_response_data(result)["months"]
    assert [(month["month"], month["assigned"]) for month in months] == [
        ("2024-03-01", "3000"),
        ("2024-02-01", "2000"),
        ("2024-01-01", "1000"),
    ]
    assert months_api.get_plan_months.call_args.args == ("test_plan_id",)


async def test_list_plan_months_excludes_deleted_months(
    months_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    months_api.get_plan_months.return_value = month_summaries(
        create_ynab_month_summary(date(2024, 1, 1)),
        create_ynab_month_summary(date(2024, 2, 1), deleted=True),
    )

    result = await mcp_client.call_tool("list_plan_months", {})

    months = extract_response_data(result)["months"]
    assert [month["month"] for month in months] == ["2024-01-01"]


async def test_list_plan_months_pages_through_months(
    months_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    months_api.get_plan_months.return_value = month_summaries(
        *(create_ynab_month_summary(date(2024, number, 1)) for number in range(1, 13))
    )

    result = await mcp_client.call_tool("list_plan_months", {"offset": 10})

    response = extract_response_data(result)
    assert [month["month"] for month in response["months"]] == [
        "2024-02-01",
        "2024-01-01",
    ]
    assert_pagination_info(
        response["pagination"], total_count=12, limit=12, offset=10, has_more=False
    )


def found_category(category: ynab.Category) -> ynab.CategoryResponse:
    """Wrap a category the way YNAB answers a lookup."""
    return ynab.CategoryResponse(data=ynab.CategoryResponseData(category=category))


async def test_get_month_category(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    groceries = create_ynab_category(
        id=uid("cat-groceries"),
        name="Groceries",
        budgeted=400_000,
        activity=-150_000,
        balance=250_000,
    )
    categories_api.get_month_category_by_id.return_value = found_category(groceries)
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(name="Everyday", categories=[groceries])
    ]

    result = await mcp_client.call_tool(
        "get_month_category",
        {"category_id": str(uid("cat-groceries")), "month": "2024-02-14"},
    )

    category = extract_response_data(result)
    assert category["category_group_name"] == "Everyday"
    assert (category["assigned"], category["activity"], category["available"]) == (
        "400",
        "-150",
        "250",
    )
    assert categories_api.get_month_category_by_id.call_args.args == (
        "test_plan_id",
        date(2024, 2, 1),
        str(uid("cat-groceries")),
    )


async def test_get_month_category_has_no_group_name_for_an_unknown_category(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    categories_api.get_month_category_by_id.return_value = found_category(
        create_ynab_category(id=uid("cat-orphan"))
    )
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            name="Everyday", categories=[create_ynab_category(id=uid("cat-other"))]
        )
    ]

    result = await mcp_client.call_tool(
        "get_month_category", {"category_id": str(uid("cat-orphan"))}
    )

    assert extract_response_data(result)["category_group_name"] is None
