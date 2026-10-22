"""
Test fixtures for YNAB MCP Server tests.

This module contains pytest fixtures for testing without calling the actual YNAB API.
"""

import sys
from collections.abc import AsyncGenerator, Generator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch
from uuid import UUID

import fastmcp
import pytest
import ynab
from fastmcp.client import Client, FastMCPTransport
from ids import uid

# Add parent directory to path to import server module
sys.path.insert(0, str(Path(__file__).parent.parent))
import server
from repository import YNABRepository


@pytest.fixture
def mock_repository() -> Generator[MagicMock, None, None]:
    """Give every tool a mock repository in place of the one plan_repository builds.

    The mock has the real repository's interface, so a test that calls a method
    the repository does not have fails.  Its api() opens a client that the
    patched ynab API classes below receive.
    """
    repository = create_autospec(YNABRepository, instance=True)
    repository.plan_id = "test_plan_id"
    repository.api.return_value.__enter__.return_value = MagicMock(spec=ynab.ApiClient)
    with patch("repository.YNABRepository", return_value=repository):
        yield repository


def patched_api[T](api_class: type[T]) -> Generator[T, None, None]:
    """Replace one ynab API class with a mock that has its interface."""
    api = create_autospec(api_class, instance=True)
    with patch(f"ynab.{api_class.__name__}", return_value=api):
        yield api


@pytest.fixture
def accounts_api() -> Generator[ynab.AccountsApi, None, None]:
    yield from patched_api(ynab.AccountsApi)


@pytest.fixture
def categories_api() -> Generator[ynab.CategoriesApi, None, None]:
    yield from patched_api(ynab.CategoriesApi)


@pytest.fixture
def months_api() -> Generator[ynab.MonthsApi, None, None]:
    yield from patched_api(ynab.MonthsApi)


@pytest.fixture
def money_movements_api() -> Generator[ynab.MoneyMovementsApi, None, None]:
    yield from patched_api(ynab.MoneyMovementsApi)


@pytest.fixture
def payees_api() -> Generator[ynab.PayeesApi, None, None]:
    yield from patched_api(ynab.PayeesApi)


@pytest.fixture
def plans_api() -> Generator[ynab.PlansApi, None, None]:
    yield from patched_api(ynab.PlansApi)


@pytest.fixture
def transactions_api() -> Generator[ynab.TransactionsApi, None, None]:
    yield from patched_api(ynab.TransactionsApi)


@pytest.fixture
def scheduled_transactions_api() -> Generator[
    ynab.ScheduledTransactionsApi, None, None
]:
    yield from patched_api(ynab.ScheduledTransactionsApi)


@pytest.fixture
async def mcp_client(
    mock_repository: MagicMock,
) -> AsyncGenerator[Client[FastMCPTransport], None]:
    """An MCP client connected in memory to the server, with a mock repository."""
    async with fastmcp.Client(server.mcp) as client:
        yield client


# Test data factories
def create_ynab_account(
    *,
    id: UUID = uid("acc-1"),
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
        transfer_payee_id=kwargs.get("transfer_payee_id", uid("transfer-payee")),
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
    id: UUID = uid("payee-1"),
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
    id: UUID = uid("cat-1"),
    name: str = "Test Category",
    category_group_id: UUID = uid("group-1"),
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
        internal=kwargs.get("internal", False),
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
    account_id: UUID = uid("acc-1"),
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


def create_ynab_category_group(
    *,
    id: UUID = uid("group-1"),
    name: str = "Test Group",
    categories: list[ynab.Category] | None = None,
    hidden: bool = False,
    deleted: bool = False,
) -> ynab.CategoryGroupWithCategories:
    """Create a YNAB category group for testing with sensible defaults."""
    return ynab.CategoryGroupWithCategories(
        id=id,
        name=name,
        hidden=hidden,
        internal=False,
        deleted=deleted,
        categories=categories or [],
    )


def saved_category(category: ynab.Category) -> ynab.SaveCategoryResponse:
    """Wrap a category the way YNAB answers a create or update."""
    return ynab.SaveCategoryResponse(
        data=ynab.SaveCategoryResponseData(category=category, server_knowledge=1)
    )


def transaction_response(txn: ynab.TransactionDetail) -> ynab.TransactionResponse:
    return ynab.TransactionResponse(
        data=ynab.TransactionResponseData(transaction=txn, server_knowledge=1)
    )


def scheduled_transaction(
    *,
    id: UUID = uid("st-rent"),
    date_first: date = date(2024, 1, 1),
    date_next: date = date(2024, 2, 1),
    frequency: str = "monthly",
    amount: int = -1_500_000,
    memo: str | None = "Rent",
    flag_color: ynab.TransactionFlagColor | None = None,
    flag_name: str | None = None,
    account_id: UUID = uid("acc-checking"),
    payee_id: UUID | None = uid("payee-landlord"),
    category_id: UUID | None = uid("cat-rent"),
    transfer_account_id: UUID | None = None,
    deleted: bool = False,
    subtransactions: list[ynab.ScheduledSubTransaction] | None = None,
) -> ynab.ScheduledTransactionDetail:
    """Build a YNAB scheduled transaction, by default a monthly rent payment."""
    return ynab.ScheduledTransactionDetail(
        id=id,
        date_first=date_first,
        date_next=date_next,
        frequency=frequency,
        amount=amount,
        memo=memo,
        flag_color=flag_color,
        flag_name=flag_name,
        account_id=account_id,
        account_name="Checking",
        payee_id=payee_id,
        payee_name="Landlord",
        category_id=category_id,
        category_name="Rent",
        transfer_account_id=transfer_account_id,
        deleted=deleted,
        subtransactions=subtransactions or [],
    )


def scheduled_part(
    name: str, amount: int, *, deleted: bool = False
) -> ynab.ScheduledSubTransaction:
    """Build one part of a split scheduled transaction."""
    return ynab.ScheduledSubTransaction(
        id=uid(name),
        scheduled_transaction_id=uid("st-rent"),
        amount=amount,
        memo=name,
        category_id=uid(f"cat-{name}"),
        category_name=name.title(),
        deleted=deleted,
    )


def scheduled_response(
    detail: ynab.ScheduledTransactionDetail,
) -> ynab.ScheduledTransactionResponse:
    return ynab.ScheduledTransactionResponse(
        data=ynab.ScheduledTransactionResponseData(scheduled_transaction=detail)
    )
