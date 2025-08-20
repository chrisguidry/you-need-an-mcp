"""
Test category-related MCP tools.
"""

from typing import Any
from unittest.mock import MagicMock

import ynab
from assertions import assert_pagination_info, extract_response_data
from fastmcp.client import Client, FastMCPTransport


def create_ynab_category(
    *,
    id: str = "cat-1",
    name: str = "Test Category",
    category_group_id: str = "group-1",
    hidden: bool = False,
    deleted: bool = False,
    budgeted: int = 50_000,  # $50.00
    activity: int = -30_000,  # -$30.00
    balance: int = 20_000,  # $20.00
    **kwargs: Any,
) -> ynab.Category:
    """Create a YNAB Category for testing with sensible defaults."""
    return ynab.Category(
        id=id,
        category_group_id=category_group_id,
        category_group_name=kwargs.get("category_group_name"),
        name=name,
        hidden=hidden,
        original_category_group_id=kwargs.get("original_category_group_id"),
        note=kwargs.get("note"),
        budgeted=budgeted,
        activity=activity,
        balance=balance,
        goal_type=kwargs.get("goal_type"),
        goal_needs_whole_amount=kwargs.get("goal_needs_whole_amount"),
        goal_day=kwargs.get("goal_day"),
        goal_cadence=kwargs.get("goal_cadence"),
        goal_cadence_frequency=kwargs.get("goal_cadence_frequency"),
        goal_creation_month=kwargs.get("goal_creation_month"),
        goal_target=kwargs.get("goal_target"),
        goal_target_month=kwargs.get("goal_target_month"),
        goal_percentage_complete=kwargs.get("goal_percentage_complete"),
        goal_months_to_budget=kwargs.get("goal_months_to_budget"),
        goal_under_funded=kwargs.get("goal_under_funded"),
        goal_overall_funded=kwargs.get("goal_overall_funded"),
        goal_overall_left=kwargs.get("goal_overall_left"),
        deleted=deleted,
    )


async def test_list_categories_success(
    mock_environment_variables: None,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful category listing."""
    visible_category = create_ynab_category(
        id="cat-1",
        name="Groceries",
        note="Food shopping",
        goal_type="TB",
        goal_target=100_000,
        goal_percentage_complete=50,
    )

    hidden_category = create_ynab_category(
        id="cat-hidden",
        name="Hidden Category",
        hidden=True,  # Should be excluded
        budgeted=10_000,
        activity=0,
        balance=10_000,
    )

    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Monthly Bills",
        hidden=False,
        deleted=False,
        categories=[visible_category, hidden_category],
    )

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[category_group], server_knowledge=0
        )
    )
    categories_api.get_categories.return_value = categories_response

    result = await mcp_client.call_tool("list_categories", {})
    response_data = extract_response_data(result)

    # Should only include visible category
    categories = response_data["categories"]
    assert len(categories) == 1
    assert categories[0]["id"] == "cat-1"
    assert categories[0]["name"] == "Groceries"
    assert categories[0]["category_group_name"] == "Monthly Bills"

    assert_pagination_info(
        response_data["pagination"],
        total_count=1,
        limit=50,
        has_more=False,
    )


async def test_list_category_groups_success(
    mock_environment_variables: None,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful category group listing."""

    category = ynab.Category(
        id="cat-1",
        category_group_id="group-1",
        category_group_name="Monthly Bills",
        name="Test Category",
        hidden=False,
        original_category_group_id=None,
        note=None,
        budgeted=50000,
        activity=-30000,
        balance=20000,
        goal_type=None,
        goal_needs_whole_amount=None,
        goal_day=None,
        goal_cadence=None,
        goal_cadence_frequency=None,
        goal_creation_month=None,
        goal_target=None,
        goal_target_month=None,
        goal_percentage_complete=None,
        goal_months_to_budget=None,
        goal_under_funded=None,
        goal_overall_funded=None,
        goal_overall_left=None,
        deleted=False,
    )

    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Monthly Bills",
        hidden=False,
        deleted=False,
        categories=[category],
    )

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[category_group], server_knowledge=0
        )
    )

    categories_api.get_categories.return_value = categories_response

    result = await mcp_client.call_tool("list_category_groups", {})

    assert len(result) == 1
    groups_data = extract_response_data(result)
    assert groups_data is not None
    # For a single category group, groups_data is the group itself
    group = groups_data
    assert group["id"] == "group-1"
    assert group["name"] == "Monthly Bills"


async def test_list_categories_filters_deleted_and_hidden(
    mock_environment_variables: None,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test that list_categories automatically filters out deleted and hidden."""

    # Active category (should be included)
    mock_active_category = ynab.Category(
        id="cat-active",
        name="Active Category",
        category_group_id="group-1",
        hidden=False,
        deleted=False,
        note="Active",
        budgeted=10000,
        activity=-5000,
        balance=5000,
        goal_type=None,
        goal_target=None,
        goal_percentage_complete=None,
        goal_under_funded=None,
        goal_creation_month=None,
        goal_target_month=None,
        goal_overall_funded=None,
        goal_overall_left=None,
    )

    # Hidden category (should be excluded)
    mock_hidden_category = ynab.Category(
        id="cat-hidden",
        name="Hidden Category",
        category_group_id="group-1",
        hidden=True,
        deleted=False,
        note="Hidden",
        budgeted=0,
        activity=0,
        balance=0,
        goal_type=None,
        goal_target=None,
        goal_percentage_complete=None,
        goal_under_funded=None,
        goal_creation_month=None,
        goal_target_month=None,
        goal_overall_funded=None,
        goal_overall_left=None,
    )

    # Deleted category (should be excluded)
    mock_deleted_category = ynab.Category(
        id="cat-deleted",
        name="Deleted Category",
        category_group_id="group-1",
        hidden=False,
        deleted=True,
        note="Deleted",
        budgeted=0,
        activity=0,
        balance=0,
        goal_type=None,
        goal_target=None,
        goal_percentage_complete=None,
        goal_under_funded=None,
        goal_creation_month=None,
        goal_target_month=None,
        goal_overall_funded=None,
        goal_overall_left=None,
    )

    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Monthly Bills",
        hidden=False,
        deleted=False,
        categories=[
            mock_active_category,
            mock_hidden_category,
            mock_deleted_category,
        ],
    )

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[category_group], server_knowledge=0
        )
    )

    categories_api.get_categories.return_value = categories_response

    result = await mcp_client.call_tool("list_categories", {})

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only include the active category
    assert len(response_data["categories"]) == 1
    assert response_data["categories"][0]["id"] == "cat-active"
    assert response_data["categories"][0]["name"] == "Active Category"


async def test_list_category_groups_filters_deleted(
    mock_environment_variables: None,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test that list_category_groups automatically filters out deleted groups."""

    # Active group (should be included)
    active_group = ynab.CategoryGroupWithCategories(
        id="group-active",
        name="Active Group",
        hidden=False,
        deleted=False,
        categories=[],
    )

    # Deleted group (should be excluded)
    deleted_group = ynab.CategoryGroupWithCategories(
        id="group-deleted",
        name="Deleted Group",
        hidden=False,
        deleted=True,
        categories=[],
    )

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[active_group, deleted_group], server_knowledge=0
        )
    )

    categories_api.get_categories.return_value = categories_response

    result = await mcp_client.call_tool("list_category_groups", {})

    assert len(result) == 1
    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only include the active group - single object
    group = response_data
    assert group["id"] == "group-active"
    assert group["name"] == "Active Group"
