"""
Categories, category groups, and their targets.

A YNAB plan sorts its categories into groups, and people think of their plan
in that hierarchy, so every category carries its group's name.  A category's
amounts are for one month: what was assigned to it, the activity against it,
and what is available.
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

from currency import currency_to_milliunits, milliunits_to_currency, optional_currency
from effects import ADDS, READ, READS, SETS, WRITE
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository

TargetFrequency = Literal["weekly", "monthly", "yearly"]


class Category(BaseModel):
    """A YNAB category with its amounts and target for one month."""

    id: UUID = Field(..., description="Unique category identifier")
    name: str = Field(..., description="Category name")
    category_group_id: UUID = Field(..., description="Category group ID")
    category_group_name: str | None = Field(None, description="Category group name")
    internal: bool = Field(
        False,
        description="Whether YNAB manages this category itself.  'Inflow: Ready to "
        "Assign' is internal: categorize income to it.",
    )
    note: str | None = Field(None, description="Category notes")
    assigned: Decimal | None = Field(None, description="Amount assigned this month")
    activity: Decimal | None = Field(
        None, description="Activity this month (negative = spending)"
    )
    available: Decimal | None = Field(
        None, description="Amount available to spend, including rollover"
    )
    target_type: str | None = Field(
        None,
        description="Target type: NEED (needed for spending, refills each period), "
        "TB (have a balance), TBD (have a balance by a date), MF (fund monthly), "
        "DEBT (pay down a debt)",
    )
    target_amount: Decimal | None = Field(None, description="Target amount")
    target_date: datetime.date | None = Field(
        None, description="Date the target should be met, for targets with a date"
    )
    target_percentage_complete: int | None = Field(
        None, description="How much of the target is funded, as a percentage"
    )
    target_underfunded: Decimal | None = Field(
        None, description="Amount still needed this month to stay on track"
    )
    target_overall_left: Decimal | None = Field(
        None, description="Amount still needed to meet the target this period"
    )

    @classmethod
    def from_ynab(
        cls, category: ynab.Category, category_group_name: str | None = None
    ) -> Category:
        """Convert a YNAB category, adding the name of its group."""
        return cls(
            id=category.id,
            name=category.name,
            category_group_id=category.category_group_id,
            category_group_name=category_group_name,
            internal=category.internal,
            note=category.note,
            assigned=optional_currency(category.budgeted),
            activity=optional_currency(category.activity),
            available=optional_currency(category.balance),
            target_type=category.goal_type,
            target_amount=optional_currency(category.goal_target),
            target_date=category.goal_target_date,
            target_percentage_complete=category.goal_percentage_complete,
            target_underfunded=optional_currency(category.goal_under_funded),
            target_overall_left=optional_currency(category.goal_overall_left),
        )


class CategoryGroup(BaseModel):
    """A YNAB category group with totals over its visible categories."""

    id: UUID = Field(..., description="Unique category group identifier")
    name: str = Field(..., description="Category group name")
    hidden: bool = Field(..., description="Whether hidden from the plan view")
    internal: bool = Field(False, description="Whether YNAB manages this group")
    category_count: int = Field(..., description="Number of visible categories")
    total_assigned: Decimal | None = Field(None, description="Total assigned")
    total_activity: Decimal | None = Field(None, description="Total activity")
    total_available: Decimal | None = Field(None, description="Total available")

    @classmethod
    def from_ynab(
        cls, category_group: ynab.CategoryGroupWithCategories
    ) -> CategoryGroup:
        """Convert a YNAB category group, totalling its visible categories."""
        visible = visible_categories(category_group.categories)
        return cls(
            id=category_group.id,
            name=category_group.name,
            hidden=category_group.hidden,
            internal=category_group.internal,
            category_count=len(visible),
            total_assigned=milliunits_to_currency(sum(c.budgeted for c in visible)),
            total_activity=milliunits_to_currency(sum(c.activity for c in visible)),
            total_available=milliunits_to_currency(sum(c.balance for c in visible)),
        )


class CategoriesResponse(BaseModel):
    """Response for list_categories tool."""

    categories: list[Category] = Field(..., description="List of categories")
    pagination: PaginationInfo = Field(..., description="Pagination information")


def visible_categories(categories: list[ynab.Category]) -> list[ynab.Category]:
    """The categories a person sees in their plan: not deleted and not hidden."""
    return [c for c in categories if not c.deleted and not c.hidden]


def category_group_names(repository: YNABRepository) -> dict[UUID, str]:
    """Map each category's ID to the name of its group."""
    return {
        category.id: group.name
        for group in repository.get_category_groups()
        for category in group.categories
    }


@tool(
    title="List categories",
    tags={"categories", READ},
    annotations=READS,
)
def list_categories(
    limit: int = 50,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> CategoriesResponse:
    """List the plan's categories with this month's amounts and targets.

    Only returns visible categories.  Hidden and deleted categories are excluded.
    Categories come in the order the plan shows them, group by group.

    Args:
        limit: Maximum number of categories to return per page (default: 50)
        offset: Number of categories to skip for pagination (default: 0)

    Returns:
        CategoriesResponse with categories list and pagination information
    """
    categories = [
        Category.from_ynab(category, group.name)
        for group in repository.get_category_groups()
        if not group.deleted
        for category in visible_categories(group.categories)
    ]
    page, pagination = paginate(categories, limit, offset)
    return CategoriesResponse(categories=page, pagination=pagination)


@tool(
    title="List category groups",
    tags={"categories", READ},
    annotations=READS,
)
def list_category_groups(
    repository: YNABRepository = Shared(plan_repository),
) -> list[CategoryGroup]:
    """List the plan's category groups with this month's totals.

    Lighter than list_categories when only the overview by group is needed.

    Returns:
        List of category groups
    """
    return [
        CategoryGroup.from_ynab(group)
        for group in repository.get_category_groups()
        if not group.deleted
    ]


def save_category(
    *,
    name: str | None,
    note: str | None,
    category_group_id: UUID | None,
    target_amount: Decimal | None,
    target_date: datetime.date | None,
    target_needs_whole_amount: bool | None,
    target_frequency: TargetFrequency | None,
) -> dict[str, object]:
    """Collect only the category fields the caller gave, in YNAB's names."""
    fields: dict[str, object] = {
        "name": name,
        "note": note,
        "category_group_id": category_group_id,
        "goal_target": (
            None if target_amount is None else currency_to_milliunits(target_amount)
        ),
        "goal_target_date": target_date,
        "goal_needs_whole_amount": target_needs_whole_amount,
        "goal_frequency": target_frequency,
    }
    return {key: value for key, value in fields.items() if value is not None}


@tool(
    title="Create category",
    tags={"categories", WRITE},
    annotations=ADDS,
)
def create_category(
    name: str,
    category_group_id: UUID,
    note: str | None = None,
    target_amount: Decimal | None = None,
    target_date: datetime.date | None = None,
    target_needs_whole_amount: bool | None = None,
    target_frequency: TargetFrequency | None = None,
    repository: YNABRepository = Shared(plan_repository),
) -> Category:
    """Create a category in a category group, optionally with a target.

    Args:
        name: Category name (required)
        category_group_id: Group to create the category in (required)
        note: Category note (optional)
        target_amount: Target amount in currency units.  Setting it on a category
                       with no target creates a monthly NEED target (optional)
        target_date: Date the target amount should be reached, for a balance by
                     a date.  Cannot be combined with target_frequency (optional)
        target_needs_whole_amount: For NEED targets, whether the whole target is
                                   needed every period (true) or the rollover
                                   counts toward it (false) (optional)
        target_frequency: Make a repeating NEED target of target_amount every
                          "weekly", "monthly", or "yearly".  Requires
                          target_amount (optional)

    Returns:
        The new category
    """
    fields = save_category(
        name=name,
        note=note,
        category_group_id=category_group_id,
        target_amount=target_amount,
        target_date=target_date,
        target_needs_whole_amount=target_needs_whole_amount,
        target_frequency=target_frequency,
    )
    with repository.api() as api_client:
        response = ynab.CategoriesApi(api_client).create_category(
            repository.plan_id,
            ynab.PostCategoryWrapper(category=ynab.NewCategory.model_validate(fields)),
        )
    repository.mark_stale("category_groups")
    category = response.data.category
    return Category.from_ynab(
        category, category_group_names(repository).get(category.id)
    )


@tool(
    title="Update category",
    tags={"categories", WRITE},
    annotations=SETS,
)
def update_category(
    category_id: UUID,
    name: str | None = None,
    note: str | None = None,
    category_group_id: UUID | None = None,
    target_amount: Decimal | None = None,
    target_date: datetime.date | None = None,
    target_needs_whole_amount: bool | None = None,
    target_frequency: TargetFrequency | None = None,
    repository: YNABRepository = Shared(plan_repository),
) -> Category:
    """Rename a category, change its note, move it to another group, or set its
    target.  Only the fields given change.

    To change what is assigned to a category, use assign_money or set_assigned.

    Args:
        category_id: Category to update (required)
        name: New category name (optional)
        note: New category note (optional)
        category_group_id: Group to move the category to (optional)
        target_amount: Target amount in currency units.  Setting it on a category
                       with no target creates a monthly NEED target (optional)
        target_date: Date the target amount should be reached, for a balance by
                     a date.  Cannot be combined with target_frequency (optional)
        target_needs_whole_amount: For NEED targets, whether the whole target is
                                   needed every period (true) or the rollover
                                   counts toward it (false) (optional)
        target_frequency: Make a repeating NEED target of target_amount every
                          "weekly", "monthly", or "yearly".  Requires
                          target_amount (optional)

    Returns:
        The updated category
    """
    fields = save_category(
        name=name,
        note=note,
        category_group_id=category_group_id,
        target_amount=target_amount,
        target_date=target_date,
        target_needs_whole_amount=target_needs_whole_amount,
        target_frequency=target_frequency,
    )
    with repository.api() as api_client:
        response = ynab.CategoriesApi(api_client).update_category(
            repository.plan_id,
            str(category_id),
            ynab.PatchCategoryWrapper(
                category=ynab.ExistingCategory.model_validate(fields)
            ),
        )
    repository.mark_stale("category_groups")
    category = response.data.category
    return Category.from_ynab(
        category, category_group_names(repository).get(category.id)
    )


class CategoryGroupSummary(BaseModel):
    """A category group's identity, as YNAB returns it after a change."""

    id: UUID = Field(..., description="Unique category group identifier")
    name: str = Field(..., description="Category group name")


@tool(
    title="Create category group",
    tags={"categories", WRITE},
    annotations=ADDS,
)
def create_category_group(
    name: str,
    repository: YNABRepository = Shared(plan_repository),
) -> CategoryGroupSummary:
    """Create an empty category group.

    Args:
        name: Group name, at most 50 characters (required)

    Returns:
        The new group's ID and name
    """
    with repository.api() as api_client:
        response = ynab.CategoriesApi(api_client).create_category_group(
            repository.plan_id,
            ynab.PostCategoryGroupWrapper(
                category_group=ynab.SaveCategoryGroup(name=name)
            ),
        )
    repository.mark_stale("category_groups")
    group = response.data.category_group
    return CategoryGroupSummary(id=group.id, name=group.name)


@tool(
    title="Rename category group",
    tags={"categories", WRITE},
    annotations=SETS,
)
def rename_category_group(
    category_group_id: UUID,
    name: str,
    repository: YNABRepository = Shared(plan_repository),
) -> CategoryGroupSummary:
    """Rename a category group.

    Args:
        category_group_id: Group to rename (required)
        name: New group name, at most 50 characters (required)

    Returns:
        The group's ID and new name
    """
    with repository.api() as api_client:
        response = ynab.CategoriesApi(api_client).update_category_group(
            repository.plan_id,
            str(category_group_id),
            ynab.PatchCategoryGroupWrapper(
                category_group=ynab.SaveCategoryGroup(name=name)
            ),
        )
    repository.mark_stale("category_groups")
    group = response.data.category_group
    return CategoryGroupSummary(id=group.id, name=group.name)


TOOLS: list[Callable[..., object]] = [
    list_categories,
    list_category_groups,
    create_category,
    update_category,
    create_category_group,
    rename_category_group,
]
