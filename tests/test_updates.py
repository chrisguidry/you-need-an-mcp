"""
Tests for update functionality in YNAB MCP Server.

Tests the update_category_budget and update_transaction tools.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import ynab
from assertions import extract_response_data
from fastmcp.client import Client, FastMCPTransport


def create_ynab_category(
    *,
    id: str = "cat-1",
    category_group_id: str = "group-1",
    budgeted: int = 100_000,  # $100.00
    activity: int = -50_000,  # -$50.00
    balance: int = 50_000,  # $50.00
    **kwargs: Any,
) -> ynab.Category:
    """Create a YNAB Category for testing with sensible defaults."""
    return ynab.Category(
        id=id,
        category_group_id=category_group_id,
        category_group_name=kwargs.get("category_group_name", "Test Group"),
        name=kwargs.get("name", "Test Category"),
        hidden=kwargs.get("hidden", False),
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
        deleted=kwargs.get("deleted", False),
    )


def create_ynab_transaction_detail(
    *,
    id: str = "txn-1",
    date: date = date(2024, 1, 15),
    amount: int = -50_000,  # -$50.00
    account_id: str = "acc-1",
    **kwargs: Any,
) -> ynab.TransactionDetail:
    """Create a YNAB TransactionDetail for testing with sensible defaults."""
    return ynab.TransactionDetail(
        id=id,
        date=date,
        amount=amount,
        memo=kwargs.get("memo"),
        cleared=kwargs.get("cleared", ynab.TransactionClearedStatus.CLEARED),
        approved=kwargs.get("approved", True),
        flag_color=kwargs.get("flag_color"),
        account_id=account_id,
        account_name=kwargs.get("account_name", "Test Account"),
        payee_id=kwargs.get("payee_id"),
        payee_name=kwargs.get("payee_name"),
        category_id=kwargs.get("category_id"),
        category_name=kwargs.get("category_name"),
        transfer_account_id=kwargs.get("transfer_account_id"),
        transfer_transaction_id=kwargs.get("transfer_transaction_id"),
        matched_transaction_id=kwargs.get("matched_transaction_id"),
        import_id=kwargs.get("import_id"),
        import_payee_name=kwargs.get("import_payee_name"),
        import_payee_name_original=kwargs.get("import_payee_name_original"),
        debt_transaction_type=kwargs.get("debt_transaction_type"),
        deleted=kwargs.get("deleted", False),
        subtransactions=kwargs.get("subtransactions", []),
    )


async def test_update_category_budget_success(
    mock_environment_variables: None,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful category budget update."""

    # Create the updated category that will be returned
    updated_category = create_ynab_category(
        id="cat-groceries",
        category_group_id="group-everyday",
        name="Groceries",
        budgeted=200_000,  # $200.00 (new budgeted amount)
        activity=-150_000,  # -$150.00
        balance=50_000,  # $50.00
    )

    # Mock the update response
    save_response = ynab.SaveCategoryResponse(
        data=ynab.SaveCategoryResponseData(
            category=updated_category, server_knowledge=0
        )
    )
    categories_api.update_month_category.return_value = save_response

    # Mock the categories response for group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-everyday",
        name="Everyday Expenses",
        hidden=False,
        deleted=False,
        categories=[updated_category],
    )
    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[category_group], server_knowledge=0
        )
    )
    categories_api.get_categories.return_value = categories_response

    # Execute the tool
    result = await mcp_client.call_tool(
        "update_category_budget",
        {
            "category_id": "cat-groceries",
            "budgeted": "200.00",
            "month": "current",
        },
    )

    # Verify the response
    assert len(result) == 1
    category_data = extract_response_data(result)
    assert category_data is not None

    assert category_data["id"] == "cat-groceries"
    assert category_data["name"] == "Groceries"
    assert category_data["category_group_name"] == "Everyday Expenses"
    assert category_data["budgeted"] == "200"  # $200.00
    assert category_data["activity"] == "-150"  # -$150.00
    assert category_data["balance"] == "50"  # $50.00

    # Verify the API was called correctly
    categories_api.update_month_category.assert_called_once()
    call_args = categories_api.update_month_category.call_args[0]
    assert call_args[0] == "test_budget_id"  # budget_id (from mock environment)
    assert call_args[1].year == 2025  # current month (from date.today())
    assert call_args[2] == "cat-groceries"  # category_id

    # Verify the patch wrapper contains correct milliunits
    patch_wrapper = call_args[3]
    assert patch_wrapper.category.budgeted == 200_000  # $200.00 in milliunits


async def test_update_transaction_success(
    mock_environment_variables: None,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test successful transaction update."""

    # Create the updated transaction that will be returned
    updated_transaction = create_ynab_transaction_detail(
        id="txn-123",
        date=date(2024, 1, 15),
        amount=-75_000,  # -$75.00
        account_id="acc-checking",
        account_name="Checking",
        payee_id="payee-amazon",
        payee_name="Amazon",
        category_id="cat-household",  # Updated category
        category_name="Household Items",  # Updated category name
        memo="Amazon purchase - household items",  # Updated memo
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
    )

    # Mock the existing transaction response (what we fetch before updating)
    original_transaction = create_ynab_transaction_detail(
        id="txn-123",
        date=date(2024, 1, 15),
        amount=-75_000,  # -$75.00
        account_id="acc-checking",
        account_name="Checking",
        payee_id="payee-amazon",
        payee_name="Amazon",
        category_id="cat-food",  # Original category
        category_name="Food",  # Original category name
        memo="Amazon purchase",  # Original memo
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
    )

    existing_transaction_response = ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=original_transaction)
    )
    transactions_api.get_transaction_by_id.return_value = existing_transaction_response

    # Mock the update response
    transaction_response = ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=updated_transaction)
    )
    transactions_api.update_transaction.return_value = transaction_response

    # Execute the tool
    result = await mcp_client.call_tool(
        "update_transaction",
        {
            "transaction_id": "txn-123",
            "category_id": "cat-household",
            "memo": "Amazon purchase - household items",
        },
    )

    # Verify the response
    assert len(result) == 1
    transaction_data = extract_response_data(result)
    assert transaction_data is not None

    assert transaction_data["id"] == "txn-123"
    assert transaction_data["amount"] == "-75"  # -$75.00
    assert transaction_data["category_id"] == "cat-household"
    assert transaction_data["category_name"] == "Household Items"
    assert transaction_data["memo"] == "Amazon purchase - household items"
    assert transaction_data["cleared"] == "cleared"

    # Verify the API was called correctly
    transactions_api.get_transaction_by_id.assert_called_once_with(
        "test_budget_id", "txn-123"
    )
    transactions_api.update_transaction.assert_called_once()
    call_args = transactions_api.update_transaction.call_args[0]
    assert call_args[0] == "test_budget_id"  # budget_id (from mock environment)
    assert call_args[1] == "txn-123"  # transaction_id

    # Verify the put wrapper contains correct data (only fields we changed)
    put_wrapper = call_args[2]
    assert put_wrapper.transaction.category_id == "cat-household"
    assert put_wrapper.transaction.memo == "Amazon purchase - household items"
    # Verify original fields are preserved
    assert put_wrapper.transaction.account_id == "acc-checking"
    assert put_wrapper.transaction.amount == -75_000


async def test_update_category_budget_with_specific_month(
    mock_environment_variables: None,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test category budget update for a specific month."""

    updated_category = create_ynab_category(
        id="cat-dining",
        name="Dining Out",
        budgeted=150_000,  # $150.00
    )

    save_response = ynab.SaveCategoryResponse(
        data=ynab.SaveCategoryResponseData(
            category=updated_category, server_knowledge=0
        )
    )
    categories_api.update_month_category.return_value = save_response

    # Mock categories response for group names
    category_group = ynab.CategoryGroupWithCategories(
        id="group-1",
        name="Fun Money",
        hidden=False,
        deleted=False,
        categories=[updated_category],
    )
    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[category_group], server_knowledge=0
        )
    )
    categories_api.get_categories.return_value = categories_response

    # Execute with specific date
    result = await mcp_client.call_tool(
        "update_category_budget",
        {
            "category_id": "cat-dining",
            "budgeted": "150.00",
            "month": "2024-03-01",  # Specific month
        },
    )

    # Verify the response
    assert len(result) == 1
    category_data = extract_response_data(result)
    assert category_data["budgeted"] == "150"

    # Verify correct month was passed to API
    call_args = categories_api.update_month_category.call_args[0]
    month_arg = call_args[1]
    assert month_arg == date(2024, 3, 1)


async def test_update_transaction_minimal_fields(
    mock_environment_variables: None,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction update with only category change."""

    # Mock the existing transaction response (what we fetch before updating)
    original_transaction = create_ynab_transaction_detail(
        id="txn-456",
        category_id="cat-food",
        category_name="Food",
    )

    existing_transaction_response = ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=original_transaction)
    )
    transactions_api.get_transaction_by_id.return_value = existing_transaction_response

    updated_transaction = create_ynab_transaction_detail(
        id="txn-456",
        category_id="cat-gas",
        category_name="Gas & Fuel",
    )

    transaction_response = ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=updated_transaction)
    )
    transactions_api.update_transaction.return_value = transaction_response

    # Execute with only category_id change
    result = await mcp_client.call_tool(
        "update_transaction",
        {
            "transaction_id": "txn-456",
            "category_id": "cat-gas",
        },
    )

    # Verify the response
    assert len(result) == 1
    transaction_data = extract_response_data(result)
    assert transaction_data["category_id"] == "cat-gas"

    # Verify only category_id was included in the update
    call_args = transactions_api.update_transaction.call_args[0]
    put_wrapper = call_args[2]
    # The wrapper should only contain category_id, not other fields
    assert put_wrapper.transaction.category_id == "cat-gas"


async def test_update_transaction_with_payee(
    mock_environment_variables: None,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    """Test transaction update with payee_id to cover all branches."""

    # Mock the existing transaction response (what we fetch before updating)
    original_transaction = create_ynab_transaction_detail(
        id="txn-789",
        amount=-25_500,  # -$25.50
        payee_id="payee-generic",
        payee_name="Generic Store",
        memo="Store purchase",
    )

    existing_transaction_response = ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=original_transaction)
    )
    transactions_api.get_transaction_by_id.return_value = existing_transaction_response

    updated_transaction = create_ynab_transaction_detail(
        id="txn-789",
        amount=-25_500,  # -$25.50
        payee_id="payee-starbucks",
        payee_name="Starbucks",
        memo="Coffee run",
    )

    transaction_response = ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=updated_transaction)
    )
    transactions_api.update_transaction.return_value = transaction_response

    # Execute with payee_id
    result = await mcp_client.call_tool(
        "update_transaction",
        {
            "transaction_id": "txn-789",
            "payee_id": "payee-starbucks",
            "memo": "Coffee run",
        },
    )

    # Verify the response
    assert len(result) == 1
    transaction_data = extract_response_data(result)
    assert transaction_data["payee_id"] == "payee-starbucks"
    assert transaction_data["memo"] == "Coffee run"
    assert transaction_data["amount"] == "-25.5"

    # Verify the API was called with correct data
    call_args = transactions_api.update_transaction.call_args[0]
    put_wrapper = call_args[2]
    assert put_wrapper.transaction.payee_id == "payee-starbucks"
    assert put_wrapper.transaction.memo == "Coffee run"
