"""
Test budget month and month category-related MCP tools.
"""

from datetime import date
from unittest.mock import MagicMock

import ynab
from assertions import extract_response_data
from fastmcp.client import Client, FastMCPTransport


async def test_get_budget_month_success(
    months_api: MagicMock,
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful budget month retrieval."""
    category = ynab.Category(
        id="cat-1",
        category_group_id="group-1",
        category_group_name="Monthly Bills",
        name="Groceries",
        hidden=False,
        original_category_group_id=None,
        note="Food",
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

    month = ynab.MonthDetail(
        month=date(2024, 1, 1),
        note="January budget",
        income=400000,
        budgeted=350000,
        activity=-200000,
        to_be_budgeted=50000,
        age_of_money=15,
        deleted=False,
        categories=[category],
    )

    # Mock repository methods
    mock_repository.get_budget_month.return_value = month

    # Mock the categories API call for getting group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Monthly Bills",
        hidden=False,
        deleted=False,
        categories=[category],
    )

    # Mock repository to return category groups
    mock_repository.get_category_groups.return_value = [category_group]

    result = await mcp_client.call_tool("get_budget_month", {})

    response_data = extract_response_data(result)
    assert response_data["note"] == "January budget"
    assert len(response_data["categories"]) == 1
    assert response_data["categories"][0]["id"] == "cat-1"
    assert response_data["categories"][0]["category_group_name"] == "Monthly Bills"


async def test_get_month_category_by_id_success(
    months_api: MagicMock,
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful month category retrieval by ID."""
    mock_category = ynab.Category(
        id="cat-1",
        category_group_id="group-1",
        category_group_name="Monthly Bills",
        name="Groceries",
        hidden=False,
        original_category_group_id=None,
        note="Food",
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

    # Mock repository method
    mock_repository.get_month_category_by_id.return_value = mock_category

    # Mock the categories API call for getting group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Monthly Bills",
        hidden=False,
        deleted=False,
        categories=[mock_category],
    )
    # Mock repository to return category groups
    mock_repository.get_category_groups.return_value = [category_group]

    result = await mcp_client.call_tool(
        "get_month_category_by_id",
        {"category_id": "cat-1"},
    )

    response_data = extract_response_data(result)
    assert response_data["id"] == "cat-1"
    assert response_data["name"] == "Groceries"
    assert response_data["category_group_name"] == "Monthly Bills"


async def test_get_month_category_by_id_default_budget(
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test month category retrieval using default budget."""
    mock_category = ynab.Category(
        id="cat-2",
        category_group_id="group-2",
        category_group_name="Fun Money",
        name="Entertainment",
        hidden=False,
        original_category_group_id=None,
        note="Fun stuff",
        budgeted=25000,
        activity=-15000,
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

    # Mock repository method
    mock_repository.get_month_category_by_id.return_value = mock_category

    # Mock the categories API call for getting group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-2",
        name="Fun Money",
        hidden=False,
        deleted=False,
        categories=[mock_category],
    )
    # Mock repository to return category groups
    mock_repository.get_category_groups.return_value = [category_group]

    # Call without budget_id to test default
    result = await mcp_client.call_tool(
        "get_month_category_by_id", {"category_id": "cat-2"}
    )

    response_data = extract_response_data(result)
    assert response_data["id"] == "cat-2"
    assert response_data["name"] == "Entertainment"
    assert response_data["category_group_name"] == "Fun Money"


async def test_get_month_category_by_id_no_groups(
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test month category retrieval when no category groups exist."""
    mock_category = ynab.Category(
        id="cat-orphan",
        category_group_id="group-missing",
        category_group_name="Missing Group",
        name="Orphan Category",
        hidden=False,
        original_category_group_id=None,
        note="Category with no group",
        budgeted=10000,
        activity=-5000,
        balance=5000,
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

    # Mock repository method
    mock_repository.get_month_category_by_id.return_value = mock_category

    # Mock empty category groups response
    mock_repository.get_category_groups.return_value = []

    result = await mcp_client.call_tool(
        "get_month_category_by_id", {"category_id": "cat-orphan"}
    )

    response_data = extract_response_data(result)
    assert response_data["id"] == "cat-orphan"
    assert response_data["category_group_name"] is None


async def test_get_month_category_by_id_category_not_in_groups(
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test month category retrieval when category is not found in any group."""
    mock_category = ynab.Category(
        id="cat-notfound",
        category_group_id="group-old",
        category_group_name="Old Group",
        name="Not Found Category",
        hidden=False,
        original_category_group_id=None,
        note="Category not in groups",
        budgeted=5000,
        activity=-2000,
        balance=3000,
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

    # Create some other categories that don't match
    other_category1 = ynab.Category(
        id="cat-other1",
        category_group_id="group-1",
        category_group_name="Group 1",
        name="Other Category 1",
        hidden=False,
        original_category_group_id=None,
        note=None,
        budgeted=0,
        activity=0,
        balance=0,
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

    other_category2 = ynab.Category(
        id="cat-other2",
        category_group_id="group-2",
        category_group_name="Group 2",
        name="Other Category 2",
        hidden=False,
        original_category_group_id=None,
        note=None,
        budgeted=0,
        activity=0,
        balance=0,
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

    # Mock repository method
    mock_repository.get_month_category_by_id.return_value = mock_category

    # Mock category groups with categories that don't include our target
    category_group1 = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Group 1",
        hidden=False,
        deleted=False,
        categories=[other_category1],
    )

    category_group2 = ynab.CategoryGroupWithCategories(
        id="group-2",
        name="Group 2",
        hidden=False,
        deleted=False,
        categories=[other_category2],
    )

    # Add an empty category group to test the empty categories branch
    empty_group = ynab.CategoryGroupWithCategories(
        id="group-empty",
        name="Empty Group",
        hidden=False,
        deleted=False,
        categories=[],
    )

    # Mock repository to return category groups
    mock_repository.get_category_groups.return_value = [
        category_group1,
        empty_group,
        category_group2,
    ]

    result = await mcp_client.call_tool(
        "get_month_category_by_id", {"category_id": "cat-notfound"}
    )

    response_data = extract_response_data(result)
    assert response_data["id"] == "cat-notfound"
    assert response_data["category_group_name"] is None


async def test_get_budget_month_with_default_budget(
    months_api: MagicMock,
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test budget month retrieval with default budget."""
    category = ynab.Category(
        id="cat-default",
        category_group_id="group-default",
        category_group_name="Default Group",
        name="Default Category",
        hidden=False,
        original_category_group_id=None,
        note=None,
        budgeted=0,
        activity=0,
        balance=0,
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

    month = ynab.MonthDetail(
        month=date(2024, 2, 1),
        note=None,
        income=0,
        budgeted=0,
        activity=0,
        to_be_budgeted=0,
        age_of_money=None,
        deleted=False,
        categories=[category],
    )

    # Mock repository method
    mock_repository.get_budget_month.return_value = month

    # Mock the categories API call for getting group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-default",
        name="Default Group",
        hidden=False,
        deleted=False,
        categories=[category],
    )
    # Mock repository to return category groups
    mock_repository.get_category_groups.return_value = [category_group]

    # Call without budget_id to test default
    result = await mcp_client.call_tool("get_budget_month", {})

    response_data = extract_response_data(result)
    assert len(response_data["categories"]) == 1
    assert response_data["categories"][0]["id"] == "cat-default"


async def test_get_budget_month_filters_deleted_and_hidden(
    months_api: MagicMock,
    categories_api: MagicMock,
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test that get_budget_month filters out deleted and hidden categories."""
    # Create active category
    active_category = ynab.Category(
        id="cat-active",
        category_group_id="group-1",
        category_group_name="Group 1",
        name="Active Category",
        hidden=False,
        original_category_group_id=None,
        note=None,
        budgeted=10000,
        activity=-5000,
        balance=5000,
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

    # Create deleted category (should be filtered out)
    deleted_category = ynab.Category(
        id="cat-deleted",
        category_group_id="group-1",
        category_group_name="Group 1",
        name="Deleted Category",
        hidden=False,
        original_category_group_id=None,
        note=None,
        budgeted=0,
        activity=0,
        balance=0,
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
        deleted=True,
    )

    # Create hidden category (should be filtered out)
    hidden_category = ynab.Category(
        id="cat-hidden",
        category_group_id="group-1",
        category_group_name="Group 1",
        name="Hidden Category",
        hidden=True,
        original_category_group_id=None,
        note=None,
        budgeted=0,
        activity=0,
        balance=0,
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

    month = ynab.MonthDetail(
        month=date(2024, 1, 1),
        note=None,
        income=100000,
        budgeted=10000,
        activity=-5000,
        to_be_budgeted=95000,
        age_of_money=10,
        deleted=False,
        categories=[active_category, deleted_category, hidden_category],
    )

    # Mock repository method
    mock_repository.get_budget_month.return_value = month

    # Mock the categories API call for getting group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Group 1",
        hidden=False,
        deleted=False,
        categories=[active_category, deleted_category, hidden_category],
    )
    # Mock repository to return category groups
    mock_repository.get_category_groups.return_value = [category_group]

    result = await mcp_client.call_tool("get_budget_month", {})

    response_data = extract_response_data(result)
    # Should only include the active category
    assert len(response_data["categories"]) == 1
    assert response_data["categories"][0]["id"] == "cat-active"
