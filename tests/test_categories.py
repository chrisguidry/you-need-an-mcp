"""
Test category-related MCP tools.
"""

import json
from unittest.mock import MagicMock

import ynab
from fastmcp import Client


async def test_list_categories_success(
    mock_environment_variables: None, categories_api: MagicMock, mcp_client: Client
):
    """Test successful category listing."""
    visible_category = ynab.Category(
        id="cat-1",
        category_group_id="group-1",
        category_group_name="Monthly Bills",
        name="Groceries",
        hidden=False,
        original_category_group_id=None,
        note="Food shopping",
        budgeted=50000,
        activity=-30000,
        balance=20000,
        goal_type="TB",
        goal_needs_whole_amount=None,
        goal_day=None,
        goal_cadence=None,
        goal_cadence_frequency=None,
        goal_creation_month=None,
        goal_target=100000,
        goal_target_month=None,
        goal_percentage_complete=50,
        goal_months_to_budget=None,
        goal_under_funded=0,
        goal_overall_funded=None,
        goal_overall_left=None,
        deleted=False,
    )

    hidden_category = ynab.Category(
        id="cat-hidden",
        category_group_id="group-1",
        category_group_name="Monthly Bills",
        name="Hidden Category",
        hidden=True,  # Should be excluded by default
        original_category_group_id=None,
        note=None,
        budgeted=10000,
        activity=0,
        balance=10000,
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
        categories=[visible_category, hidden_category],
    )

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[category_group], server_knowledge=0
        )
    )

    categories_api.get_categories.return_value = categories_response

    result = await mcp_client.call_tool("list_categories", {})

    assert len(result) == 1
    response_data = json.loads(result[0].text)
    # Should only include visible category
    assert len(response_data["categories"]) == 1
    assert response_data["categories"][0]["id"] == "cat-1"
    assert response_data["categories"][0]["name"] == "Groceries"


async def test_list_category_groups_success(
    mock_environment_variables: None, categories_api: MagicMock, mcp_client: Client
):
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
    groups_data = json.loads(result[0].text)
    # groups_data is a single group object
    assert groups_data["id"] == "group-1"
    assert groups_data["name"] == "Monthly Bills"


async def test_list_categories_filters_deleted_and_hidden(
    mock_environment_variables: None, categories_api: MagicMock, mcp_client: Client
):
    """Test that list_categories automatically filters out deleted and hidden categories."""

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
    response_data = json.loads(result[0].text)
    # Should only include the active category
    assert len(response_data["categories"]) == 1
    assert response_data["categories"][0]["id"] == "cat-active"
    assert response_data["categories"][0]["name"] == "Active Category"


async def test_list_category_groups_filters_deleted(
    mock_environment_variables: None, categories_api: MagicMock, mcp_client: Client
):
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
    response_data = json.loads(result[0].text)
    # Should only include the active group (returns single group object when filtered to one)
    assert response_data["id"] == "group-active"
    assert response_data["name"] == "Active Group"
