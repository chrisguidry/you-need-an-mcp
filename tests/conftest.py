"""
Test fixtures for YNAB MCP Server tests.

This module contains pytest fixtures for testing without calling the actual YNAB API.
"""

import sys
from collections.abc import AsyncGenerator, Generator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import fastmcp
import pytest
import ynab
from fastmcp.client import Client, FastMCPTransport

# Add parent directory to path to import server module
sys.path.insert(0, str(Path(__file__).parent.parent))
import server


@pytest.fixture
def mock_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock environment variables for testing."""
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token_123")
    monkeypatch.setenv("YNAB_BUDGET", "test_budget_id")


@pytest.fixture
def ynab_client(mock_environment_variables: None) -> Generator[MagicMock, None, None]:
    """Mock YNAB client with proper autospec for testing."""
    mock_client = MagicMock(spec=ynab.ApiClient)
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    yield mock_client


@pytest.fixture
def mock_repository() -> Generator[MagicMock, None, None]:
    """Mock the repository to prevent API calls during testing."""
    with patch("server._repository") as mock_repo:
        yield mock_repo


@pytest.fixture
def categories_api(ynab_client: MagicMock) -> Generator[MagicMock, None, None]:
    mock_api = Mock(spec=ynab.CategoriesApi)
    with patch("ynab.CategoriesApi", return_value=mock_api):
        yield mock_api


@pytest.fixture
async def mcp_client() -> AsyncGenerator[Client[FastMCPTransport], None]:
    """Mock MCP client with proper autospec for testing."""
    async with fastmcp.Client(server.mcp) as client:
        yield client


# Test data factories
def create_ynab_account(
    *,
    id: str = "acc-1",
    name: str = "Test Account",
    account_type: ynab.AccountType = ynab.AccountType.CHECKING,
    on_budget: bool = True,
    closed: bool = False,
    balance: int = 100_000,
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.Account:
    """Create a YNAB Account for testing with sensible defaults."""
    return ynab.Account(
        id=id,
        name=name,
        type=account_type,
        on_budget=on_budget,
        closed=closed,
        note=kwargs.get("note"),
        balance=balance,
        cleared_balance=kwargs.get("cleared_balance", balance - 5_000),
        uncleared_balance=kwargs.get("uncleared_balance", 5_000),
        transfer_payee_id=kwargs.get("transfer_payee_id"),
        direct_import_linked=kwargs.get("direct_import_linked", False),
        direct_import_in_error=kwargs.get("direct_import_in_error", False),
        last_reconciled_at=kwargs.get("last_reconciled_at"),
        debt_original_balance=kwargs.get("debt_original_balance"),
        debt_interest_rates=kwargs.get("debt_interest_rates"),
        debt_minimum_payments=kwargs.get("debt_minimum_payments"),
        debt_escrow_amounts=kwargs.get("debt_escrow_amounts"),
        deleted=deleted,
    )


def create_ynab_payee(
    *,
    id: str = "payee-1",
    name: str = "Test Payee",
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.Payee:
    """Create a YNAB Payee for testing with sensible defaults."""
    return ynab.Payee(
        id=id,
        name=name,
        transfer_account_id=kwargs.get("transfer_account_id"),
        deleted=deleted,
    )


def create_ynab_category(
    *,
    id: str = "cat-1",
    name: str = "Test Category",
    category_group_id: str = "group-1",
    hidden: bool = False,
    deleted: bool = False,
    budgeted: int = 50_000,
    activity: int = -30_000,
    balance: int = 20_000,
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


def create_ynab_transaction(
    *,
    id: str = "txn-1",
    transaction_date: date = date(2024, 1, 15),
    amount: int = -50_000,
    account_id: str = "acc-1",
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.TransactionDetail:
    """Create a YNAB TransactionDetail for testing with sensible defaults."""
    return ynab.TransactionDetail(
        id=id,
        date=transaction_date,
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
        deleted=deleted,
        subtransactions=kwargs.get("subtransactions", []),
    )
