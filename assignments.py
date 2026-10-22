"""
Assigning money to categories, and moving it between them.

YNAB's API has one write for this: set a category's assigned amount for a
month.  Assigning more, assigning less, and moving money are all built on it.
Every tool here reports each category it changed, with the amount assigned
before and after, so the model can tell the user exactly what moved.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import ynab
from fastmcp.dependencies import Shared
from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from currency import currency_to_milliunits, milliunits_to_currency
from effects import ADJUSTS, READ, READS, SETS, WRITE
from months import Month, fetch_month_category, resolve_month
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository

logger = logging.getLogger(__name__)

READY_TO_ASSIGN = "Ready to Assign"


class AssignmentChange(BaseModel):
    """How one category's assigned amount changed."""

    category_id: UUID = Field(..., description="Category that changed")
    category_name: str = Field(..., description="Category name")
    month: datetime.date = Field(..., description="Plan month that changed")
    assigned_before: Decimal = Field(..., description="Assigned before the change")
    assigned_after: Decimal = Field(..., description="Assigned after the change")
    available_after: Decimal = Field(..., description="Available after the change")


class AssignmentResult(BaseModel):
    """The categories an assignment changed."""

    changes: list[AssignmentChange] = Field(
        ..., description="Each category that changed, in the order they changed"
    )


def write_assigned(
    repository: YNABRepository,
    month: datetime.date,
    category: ynab.Category,
    assigned_milliunits: int,
) -> AssignmentChange:
    """Set one category's assigned amount and describe the change."""
    with repository.api() as api_client:
        response = ynab.CategoriesApi(api_client).update_month_category(
            repository.plan_id,
            month,
            str(category.id),
            ynab.PatchMonthCategoryWrapper(
                category=ynab.SaveMonthCategory(budgeted=assigned_milliunits)
            ),
        )
    repository.mark_stale("category_groups")
    updated = response.data.category
    return AssignmentChange(
        category_id=updated.id,
        category_name=updated.name,
        month=month,
        assigned_before=milliunits_to_currency(category.budgeted),
        assigned_after=milliunits_to_currency(updated.budgeted),
        available_after=milliunits_to_currency(updated.balance),
    )


@tool(title="Assign money", tags={"assignments", WRITE}, annotations=ADJUSTS)
def assign_money(
    category_id: UUID,
    amount: Decimal,
    month: Month = "current",
    repository: YNABRepository = Shared(plan_repository),
) -> AssignmentResult:
    """Assign more money to a category from Ready to Assign, or take some back.

    This adds to what is already assigned: assigning 100 to a category with 250
    assigned leaves 350 assigned.  A negative amount returns money to Ready to
    Assign.  Calling this twice assigns twice, so do not retry it blindly after
    an error; check the category with get_month_category first.

    For categories with NEED targets that refill each month, the full target is
    usually assigned every month, whatever is available.

    Args:
        category_id: Category to assign to (required)
        amount: Amount in currency units to add to the assigned amount.  Negative
            takes money back to Ready to Assign (required)
        month: Which plan month (default: "current"):
            • "current": This calendar month
            • "last": The previous calendar month
            • "next": The next calendar month
            • A date: The month containing that date, such as 2024-03-01

    Returns:
        AssignmentResult with the category's assigned amount before and after
    """
    plan_month = resolve_month(month)
    category = fetch_month_category(repository, plan_month, category_id)
    assigned = category.budgeted + currency_to_milliunits(amount)
    return AssignmentResult(
        changes=[write_assigned(repository, plan_month, category, assigned)]
    )


@tool(title="Set assigned amount", tags={"assignments", WRITE}, annotations=SETS)
def set_assigned(
    category_id: UUID,
    amount: Decimal,
    month: Month = "current",
    repository: YNABRepository = Shared(plan_repository),
) -> AssignmentResult:
    """Set exactly how much is assigned to a category in a month.

    Unlike assign_money, this replaces the assigned amount, so it is safe to
    retry.  Ready to Assign absorbs the difference.

    Args:
        category_id: Category to set (required)
        amount: The category's new assigned amount in currency units (required)
        month: Which plan month (default: "current"):
            • "current": This calendar month
            • "last": The previous calendar month
            • "next": The next calendar month
            • A date: The month containing that date, such as 2024-03-01

    Returns:
        AssignmentResult with the category's assigned amount before and after
    """
    plan_month = resolve_month(month)
    category = fetch_month_category(repository, plan_month, category_id)
    assigned = currency_to_milliunits(amount)
    return AssignmentResult(
        changes=[write_assigned(repository, plan_month, category, assigned)]
    )


@tool(title="Move money", tags={"assignments", WRITE}, annotations=ADJUSTS)
def move_money(
    from_category_id: UUID,
    to_category_id: UUID,
    amount: Decimal,
    month: Month = "current",
    repository: YNABRepository = Shared(plan_repository),
) -> AssignmentResult:
    """Move assigned money from one category to another within a month.

    This is how to cover overspending or reallocate: it takes the amount off
    one category's assigned amount and adds it to the other's.  Ready to Assign
    does not change.  If YNAB rejects the second change, the first is put back
    before the error is reported.

    Args:
        from_category_id: Category to take the money from (required)
        to_category_id: Category to give the money to (required)
        amount: Amount in currency units to move, greater than zero (required)
        month: Which plan month (default: "current"):
            • "current": This calendar month
            • "last": The previous calendar month
            • "next": The next calendar month
            • A date: The month containing that date, such as 2024-03-01

    Returns:
        AssignmentResult with both categories' assigned amounts before and after
    """
    if amount <= 0:
        raise ToolError("amount must be greater than zero")
    if from_category_id == to_category_id:
        raise ToolError("from_category_id and to_category_id must differ")

    plan_month = resolve_month(month)
    milliunits = currency_to_milliunits(amount)
    source = fetch_month_category(repository, plan_month, from_category_id)
    target = fetch_month_category(repository, plan_month, to_category_id)

    taken = write_assigned(repository, plan_month, source, source.budgeted - milliunits)
    try:
        given = write_assigned(
            repository, plan_month, target, target.budgeted + milliunits
        )
    except Exception:
        logger.warning("Putting back the first half of a failed move")
        write_assigned(repository, plan_month, source, source.budgeted)
        raise

    return AssignmentResult(changes=[taken, given])


class MoneyMovement(BaseModel):
    """Money moved between categories, or between a category and Ready to Assign."""

    moved_at: datetime.datetime | None = Field(None, description="When it moved")
    month: datetime.date | None = Field(None, description="Plan month it moved in")
    amount: Decimal = Field(..., description="Amount moved in currency units")
    from_category_id: UUID | None = Field(
        None, description="Category it came from, or null for Ready to Assign"
    )
    from_category_name: str = Field(..., description="Where the money came from")
    to_category_id: UUID | None = Field(
        None, description="Category it went to, or null for Ready to Assign"
    )
    to_category_name: str = Field(..., description="Where the money went")
    note: str | None = Field(None, description="Note left with the movement")


class MoneyMovementsResponse(BaseModel):
    """Response for list_money_movements tool."""

    money_movements: list[MoneyMovement] = Field(
        ..., description="Money movements, most recent first"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")


@tool(title="List money movements", tags={"assignments", READ}, annotations=READS)
def list_money_movements(
    month: Month | None = "current",
    limit: int = 50,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> MoneyMovementsResponse:
    """List the history of money assigned and moved between categories.

    Use this to explain why a category's assigned amount changed: each entry
    says how much moved, from where, to where, and when.

    Args:
        month: Which plan month (default: "current"), or null for every month:
            • "current": This calendar month
            • "last": The previous calendar month
            • "next": The next calendar month
            • A date: The month containing that date, such as 2024-03-01
        limit: Maximum number of movements to return per page (default: 50)
        offset: Number of movements to skip for pagination (default: 0)

    Returns:
        MoneyMovementsResponse with movements and pagination information
    """
    with repository.api() as api_client:
        api = ynab.MoneyMovementsApi(api_client)
        if month is None:
            response = api.get_money_movements(repository.plan_id)
        else:
            response = api.get_money_movements_by_month(
                repository.plan_id, resolve_month(month)
            )

    names = category_names(repository)

    def name_of(category_id: UUID | None) -> str:
        if category_id is None:
            return READY_TO_ASSIGN
        return names.get(category_id, "Unknown category")

    movements = [
        MoneyMovement(
            moved_at=movement.moved_at,
            month=movement.month,
            amount=milliunits_to_currency(movement.amount),
            from_category_id=movement.from_category_id,
            from_category_name=name_of(movement.from_category_id),
            to_category_id=movement.to_category_id,
            to_category_name=name_of(movement.to_category_id),
            note=movement.note,
        )
        for movement in response.data.money_movements
    ]
    movements.sort(
        key=lambda movement: movement.moved_at
        or datetime.datetime.min.replace(tzinfo=datetime.UTC),
        reverse=True,
    )
    page, pagination = paginate(movements, limit, offset)
    return MoneyMovementsResponse(money_movements=page, pagination=pagination)


def category_names(repository: YNABRepository) -> dict[UUID, str]:
    """Map each category's ID to its name."""
    return {
        category.id: category.name
        for group in repository.get_category_groups()
        for category in group.categories
    }


TOOLS: list[Callable[..., object]] = [
    assign_money,
    set_assigned,
    move_money,
    list_money_movements,
]
