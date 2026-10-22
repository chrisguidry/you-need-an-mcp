"""
Plan months: what was assigned, spent, and left to assign in each month.

People talk about months relatively ("this month", "last month"), so every tool
that takes a month also accepts "current", "last", and "next".
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal
from typing import Literal
from uuid import UUID

import ynab
from fastmcp.dependencies import Shared
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from categories import Category, category_group_names, visible_categories
from currency import milliunits_to_currency
from effects import READ, READS
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository

Month = datetime.date | Literal["current", "last", "next"]


def resolve_month(month: Month, today: datetime.date | None = None) -> datetime.date:
    """Return the first day of the month that a month argument names."""
    if isinstance(month, datetime.date):
        return month.replace(day=1)

    today = today or datetime.date.today()
    first = today.replace(day=1)
    match month:
        case "current":
            return first
        case "last":
            return (first - datetime.timedelta(days=1)).replace(day=1)
        case "next":
            return (first + datetime.timedelta(days=32)).replace(day=1)
        case _:
            raise ValueError(f"Invalid month value: {month}")


class MonthSummary(BaseModel):
    """The plan-wide totals for one month."""

    month: datetime.date = Field(..., description="First day of the plan month")
    note: str | None = Field(None, description="The user's note for this month")
    income: Decimal = Field(
        ..., description="Income categorized to 'Inflow: Ready to Assign'"
    )
    assigned: Decimal = Field(..., description="Total assigned across categories")
    activity: Decimal = Field(
        ..., description="Total activity, excluding income to Ready to Assign"
    )
    ready_to_assign: Decimal = Field(
        ..., description="Money not yet assigned to a category (can be negative)"
    )
    age_of_money: int | None = Field(
        None, description="Age of money in days: how long money sits before it is spent"
    )

    @classmethod
    def from_ynab(cls, month: ynab.MonthSummary | ynab.MonthDetail) -> MonthSummary:
        """Convert a YNAB month."""
        return cls(
            month=month.month,
            note=month.note,
            income=milliunits_to_currency(month.income),
            assigned=milliunits_to_currency(month.budgeted),
            activity=milliunits_to_currency(month.activity),
            ready_to_assign=milliunits_to_currency(month.to_be_budgeted),
            age_of_money=month.age_of_money,
        )


class PlanMonth(MonthSummary):
    """One plan month with its totals and its categories."""

    categories: list[Category] = Field(
        ..., description="Categories with their amounts for this month"
    )
    pagination: PaginationInfo = Field(
        ..., description="Pagination information for the categories"
    )


class MonthsResponse(BaseModel):
    """Response for list_plan_months tool."""

    months: list[MonthSummary] = Field(..., description="Months, newest first")
    pagination: PaginationInfo = Field(..., description="Pagination information")


@tool(title="Get plan month", tags={"months", READ}, annotations=READS)
def get_plan_month(
    month: Month = "current",
    limit: int = 50,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> PlanMonth:
    """Get one month of the plan: income, assigned, activity, Ready to Assign,
    age of money, and each visible category's amounts for that month.

    Args:
        month: Which plan month (default: "current"):
            • "current": This calendar month
            • "last": The previous calendar month
            • "next": The next calendar month
            • A date: The month containing that date, such as 2024-03-01
        limit: Maximum number of categories to return per page (default: 50)
        offset: Number of categories to skip for pagination (default: 0)

    Returns:
        PlanMonth with the month's totals, its categories, and pagination
    """
    with repository.api() as api_client:
        response = ynab.MonthsApi(api_client).get_plan_month(
            repository.plan_id, resolve_month(month)
        )
    plan_month = response.data.month

    group_names = category_group_names(repository)
    categories = [
        Category.from_ynab(category, group_names.get(category.id))
        for category in visible_categories(plan_month.categories)
    ]
    page, pagination = paginate(categories, limit, offset)

    return PlanMonth(
        **MonthSummary.from_ynab(plan_month).model_dump(),
        categories=page,
        pagination=pagination,
    )


@tool(title="List plan months", tags={"months", READ}, annotations=READS)
def list_plan_months(
    limit: int = 12,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> MonthsResponse:
    """List the plan's months with their totals, newest first.

    Use this for trends over time: income, assigned, and activity by month, how
    Ready to Assign changed, and how age of money moved.

    Args:
        limit: Maximum number of months to return per page (default: 12)
        offset: Number of months to skip for pagination (default: 0)

    Returns:
        MonthsResponse with month totals and pagination information
    """
    with repository.api() as api_client:
        response = ynab.MonthsApi(api_client).get_plan_months(repository.plan_id)

    months = [
        MonthSummary.from_ynab(month)
        for month in response.data.months
        if not month.deleted
    ]
    months.sort(key=lambda summary: summary.month, reverse=True)
    page, pagination = paginate(months, limit, offset)
    return MonthsResponse(months=page, pagination=pagination)


def fetch_month_category(
    repository: YNABRepository, month: datetime.date, category_id: UUID
) -> ynab.Category:
    """Fetch one category's amounts for one month from YNAB."""
    with repository.api() as api_client:
        response = ynab.CategoriesApi(api_client).get_month_category_by_id(
            repository.plan_id, month, str(category_id)
        )
    return response.data.category


@tool(title="Get month category", tags={"months", READ}, annotations=READS)
def get_month_category(
    category_id: UUID,
    month: Month = "current",
    repository: YNABRepository = Shared(plan_repository),
) -> Category:
    """Get one category's assigned, activity, available, and target for a month.

    Args:
        category_id: Category to look up (required)
        month: Which plan month (default: "current"):
            • "current": This calendar month
            • "last": The previous calendar month
            • "next": The next calendar month
            • A date: The month containing that date, such as 2024-03-01

    Returns:
        Category with its amounts for that month
    """
    category = fetch_month_category(repository, resolve_month(month), category_id)
    return Category.from_ynab(
        category, category_group_names(repository).get(category.id)
    )


TOOLS: list[Callable[..., object]] = [
    get_plan_month,
    list_plan_months,
    get_month_category,
]
