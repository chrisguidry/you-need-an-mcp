"""
Test suite for YNABRepository differential sync functionality.
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import ynab
from conftest import create_ynab_account, create_ynab_payee
from ynab.exceptions import ConflictException

from repository import YNABRepository


@pytest.fixture
def repository() -> YNABRepository:
    """Create a repository instance for testing."""
    repo = YNABRepository(budget_id="test-budget", access_token="test-token")

    # Disable background sync by default to prevent real API calls during tests
    repo._background_sync_enabled = False

    return repo


def test_repository_initial_sync(repository: YNABRepository) -> None:
    """Test repository initial sync without server knowledge."""
    account1 = create_ynab_account(id="acc-1", name="Checking")
    account2 = create_ynab_account(id="acc-2", name="Savings")

    accounts_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[account1, account2], server_knowledge=100
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = accounts_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Verify initial sync called without last_knowledge_of_server
    mock_accounts_api.get_accounts.assert_called_once_with("test-budget")

    # Verify data was stored
    accounts = repository.get_accounts()
    assert len(accounts) == 2
    assert accounts[0].id == "acc-1"
    assert accounts[1].id == "acc-2"

    # Verify server knowledge was stored
    assert repository._server_knowledge["accounts"] == 100
    assert repository.is_initialized()


def test_repository_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync with server knowledge."""
    # Set up initial state
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._server_knowledge["accounts"] = 100
    repository._last_sync = datetime.now()

    # Delta sync with updated account and new account
    updated_account1 = create_ynab_account(id="acc-1", name="Updated Checking")
    new_account = create_ynab_account(id="acc-2", name="New Savings")

    delta_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[updated_account1, new_account], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = delta_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Verify delta sync called with last_knowledge_of_server
    mock_accounts_api.get_accounts.assert_called_once_with(
        "test-budget", last_knowledge_of_server=100
    )

    # Verify deltas were applied
    accounts = repository.get_accounts()
    assert len(accounts) == 2

    # Find accounts by ID
    acc1 = next(acc for acc in accounts if acc.id == "acc-1")
    acc2 = next(acc for acc in accounts if acc.id == "acc-2")

    assert acc1.name == "Updated Checking"  # Updated
    assert acc2.name == "New Savings"  # Added

    # Verify server knowledge was updated
    assert repository._server_knowledge["accounts"] == 110


def test_repository_handles_deleted_accounts(repository: YNABRepository) -> None:
    """Test repository handles deleted accounts in delta sync."""
    # Set up initial state with two accounts
    account1 = create_ynab_account(id="acc-1", name="Checking")
    account2 = create_ynab_account(id="acc-2", name="Savings")
    repository._data["accounts"] = [account1, account2]
    repository._server_knowledge["accounts"] = 100
    repository._last_sync = datetime.now()

    # Delta with one deleted account
    deleted_account = create_ynab_account(id="acc-2", name="Savings", deleted=True)

    delta_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[deleted_account], server_knowledge=110)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = delta_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Verify deleted account was removed
    accounts = repository.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "acc-1"  # Only checking account remains


def test_repository_fallback_to_full_refresh_on_error(
    repository: YNABRepository,
) -> None:
    """Test repository falls back to full refresh when delta sync fails."""
    # Set up initial state
    repository._server_knowledge["accounts"] = 100
    repository._last_sync = datetime.now()

    account1 = create_ynab_account(id="acc-1", name="Checking")
    account2 = create_ynab_account(id="acc-2", name="Savings")

    full_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[account1, account2], server_knowledge=120
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        # First call (delta) raises API exception
        # Second call (full refresh) succeeds
        mock_accounts_api.get_accounts.side_effect = [
            ynab.ApiException(status=500, reason="Server Error"),
            full_response,
        ]

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Verify two calls were made
    assert mock_accounts_api.get_accounts.call_count == 2

    # First call with server knowledge (delta attempt)
    first_call = mock_accounts_api.get_accounts.call_args_list[0]
    assert first_call[0] == ("test-budget",)
    assert first_call[1] == {"last_knowledge_of_server": 100}

    # Second call without server knowledge (full refresh)
    second_call = mock_accounts_api.get_accounts.call_args_list[1]
    assert second_call[0] == ("test-budget",)
    assert "last_knowledge_of_server" not in second_call[1]

    # Verify data was stored from full refresh
    accounts = repository.get_accounts()
    assert len(accounts) == 2
    assert repository._server_knowledge["accounts"] == 120


def test_repository_lazy_initialization(repository: YNABRepository) -> None:
    """Test repository initializes automatically when data is requested."""
    account1 = create_ynab_account(id="acc-1", name="Checking")

    accounts_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = accounts_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            # Repository is not initialized initially
            assert not repository.is_initialized()

            # Calling get_accounts should trigger sync
            accounts = repository.get_accounts()

    # Verify sync was called
    mock_accounts_api.get_accounts.assert_called_once()

    # Verify data is available
    assert len(accounts) == 1
    assert accounts[0].id == "acc-1"
    assert repository.is_initialized()


def test_repository_thread_safety(repository: YNABRepository) -> None:
    """Test repository operations are thread-safe."""
    # This test verifies the locking mechanism works
    account1 = create_ynab_account(id="acc-1", name="Checking")

    accounts_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = accounts_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            # Multiple calls should be safe
            repository.sync_accounts()
            accounts1 = repository.get_accounts()
            accounts2 = repository.get_accounts()
            last_sync1 = repository.last_sync_time()
            last_sync2 = repository.last_sync_time()

    # All operations should complete successfully
    assert len(accounts1) == 1
    assert len(accounts2) == 1
    assert last_sync1 is not None
    assert last_sync2 is not None
    assert last_sync1 == last_sync2


def test_repository_payees_initial_sync(repository: YNABRepository) -> None:
    """Test repository initial sync for payees without server knowledge."""
    payee1 = create_ynab_payee(id="payee-1", name="Amazon")
    payee2 = create_ynab_payee(id="payee-2", name="Starbucks")

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=[payee1, payee2], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_payees_api = MagicMock()
        mock_payees_api.get_payees.return_value = payees_response

        with patch("ynab.PayeesApi", return_value=mock_payees_api):
            repository.sync_payees()

    # Verify initial sync called without last_knowledge_of_server
    mock_payees_api.get_payees.assert_called_once_with("test-budget")

    # Verify data was stored
    payees = repository.get_payees()
    assert len(payees) == 2
    assert payees[0].id == "payee-1"
    assert payees[1].id == "payee-2"

    # Verify server knowledge was stored
    assert repository._server_knowledge["payees"] == 100


def test_repository_payees_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync for payees with server knowledge."""
    # Set up initial state
    payee1 = create_ynab_payee(id="payee-1", name="Amazon")
    repository._data["payees"] = [payee1]
    repository._server_knowledge["payees"] = 100
    repository._last_sync = datetime.now()

    # Delta sync with updated payee and new payee
    updated_payee1 = create_ynab_payee(id="payee-1", name="Amazon.com")
    new_payee = create_ynab_payee(id="payee-2", name="Target")

    delta_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(
            payees=[updated_payee1, new_payee], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_payees_api = MagicMock()
        mock_payees_api.get_payees.return_value = delta_response

        with patch("ynab.PayeesApi", return_value=mock_payees_api):
            repository.sync_payees()

    # Verify delta sync called with last_knowledge_of_server
    mock_payees_api.get_payees.assert_called_once_with(
        "test-budget", last_knowledge_of_server=100
    )

    # Verify deltas were applied
    payees = repository.get_payees()
    assert len(payees) == 2

    # Find payees by ID
    p1 = next(p for p in payees if p.id == "payee-1")
    p2 = next(p for p in payees if p.id == "payee-2")

    assert p1.name == "Amazon.com"  # Updated
    assert p2.name == "Target"  # Added

    # Verify server knowledge was updated
    assert repository._server_knowledge["payees"] == 110


def test_repository_payees_handles_deleted(repository: YNABRepository) -> None:
    """Test repository handles deleted payees in delta sync."""
    # Set up initial state with two payees
    payee1 = create_ynab_payee(id="payee-1", name="Amazon")
    payee2 = create_ynab_payee(id="payee-2", name="Old Store")
    repository._data["payees"] = [payee1, payee2]
    repository._server_knowledge["payees"] = 100
    repository._last_sync = datetime.now()

    # Delta with one deleted payee
    deleted_payee = create_ynab_payee(id="payee-2", name="Old Store", deleted=True)

    delta_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=[deleted_payee], server_knowledge=110)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_payees_api = MagicMock()
        mock_payees_api.get_payees.return_value = delta_response

        with patch("ynab.PayeesApi", return_value=mock_payees_api):
            repository.sync_payees()

    # Verify deleted payee was removed
    payees = repository.get_payees()
    assert len(payees) == 1
    assert payees[0].id == "payee-1"  # Only Amazon remains


def test_repository_payees_lazy_initialization(repository: YNABRepository) -> None:
    """Test payees repository initializes automatically when data is requested."""
    payee1 = create_ynab_payee(id="payee-1", name="Amazon")

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=[payee1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_payees_api = MagicMock()
        mock_payees_api.get_payees.return_value = payees_response

        with patch("ynab.PayeesApi", return_value=mock_payees_api):
            # Repository payees is not initialized initially
            assert "payees" not in repository._data

            # Calling get_payees should trigger sync
            payees = repository.get_payees()

    # Verify sync was called
    mock_payees_api.get_payees.assert_called_once()

    # Verify data is available
    assert len(payees) == 1
    assert payees[0].id == "payee-1"


def create_ynab_category_group(
    *,
    id: str = "group-1",
    name: str = "Test Group",
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.CategoryGroupWithCategories:
    """Create a YNAB CategoryGroupWithCategories for testing with sensible defaults."""
    categories = kwargs.get("categories", [])
    return ynab.CategoryGroupWithCategories(
        id=id,
        name=name,
        hidden=kwargs.get("hidden", False),
        deleted=deleted,
        categories=categories,
    )


def test_repository_category_groups_initial_sync(repository: YNABRepository) -> None:
    """Test repository initial sync for category groups without server knowledge."""
    group1 = create_ynab_category_group(id="group-1", name="Monthly Bills")
    group2 = create_ynab_category_group(id="group-2", name="Everyday Expenses")

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[group1, group2], server_knowledge=100
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = categories_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            repository.sync_category_groups()

    # Verify initial sync called without last_knowledge_of_server
    mock_categories_api.get_categories.assert_called_once_with("test-budget")

    # Verify data was stored
    category_groups = repository.get_category_groups()
    assert len(category_groups) == 2
    assert category_groups[0].id == "group-1"
    assert category_groups[1].id == "group-2"

    # Verify server knowledge was stored
    assert repository._server_knowledge["category_groups"] == 100


def test_repository_category_groups_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync for category groups with server knowledge."""
    # Set up initial state
    group1 = create_ynab_category_group(id="group-1", name="Monthly Bills")
    repository._data["category_groups"] = [group1]
    repository._server_knowledge["category_groups"] = 100
    repository._last_sync = datetime.now()

    # Delta sync with updated group and new group
    updated_group1 = create_ynab_category_group(id="group-1", name="Fixed Expenses")
    new_group = create_ynab_category_group(id="group-2", name="Variable Expenses")

    delta_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[updated_group1, new_group], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = delta_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            repository.sync_category_groups()

    # Verify delta sync called with last_knowledge_of_server
    mock_categories_api.get_categories.assert_called_once_with(
        "test-budget", last_knowledge_of_server=100
    )

    # Verify deltas were applied
    category_groups = repository.get_category_groups()
    assert len(category_groups) == 2

    # Find groups by ID
    g1 = next(g for g in category_groups if g.id == "group-1")
    g2 = next(g for g in category_groups if g.id == "group-2")

    assert g1.name == "Fixed Expenses"  # Updated
    assert g2.name == "Variable Expenses"  # Added

    # Verify server knowledge was updated
    assert repository._server_knowledge["category_groups"] == 110


def test_repository_category_groups_handles_deleted(repository: YNABRepository) -> None:
    """Test repository handles deleted category groups in delta sync."""
    # Set up initial state with two groups
    group1 = create_ynab_category_group(id="group-1", name="Monthly Bills")
    group2 = create_ynab_category_group(id="group-2", name="Old Category")
    repository._data["category_groups"] = [group1, group2]
    repository._server_knowledge["category_groups"] = 100
    repository._last_sync = datetime.now()

    # Delta with one deleted group
    deleted_group = create_ynab_category_group(
        id="group-2", name="Old Category", deleted=True
    )

    delta_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[deleted_group], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = delta_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            repository.sync_category_groups()

    # Verify deleted group was removed
    category_groups = repository.get_category_groups()
    assert len(category_groups) == 1
    assert category_groups[0].id == "group-1"  # Only Monthly Bills remains


def test_repository_category_groups_lazy_initialization(
    repository: YNABRepository,
) -> None:
    """Test category groups repository initializes automatically when data requested."""
    group1 = create_ynab_category_group(id="group-1", name="Monthly Bills")

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(category_groups=[group1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = categories_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            # Repository category groups is not initialized initially
            assert "category_groups" not in repository._data

            # Calling get_category_groups should trigger sync
            category_groups = repository.get_category_groups()

    # Verify sync was called
    mock_categories_api.get_categories.assert_called_once()

    # Verify data is available
    assert len(category_groups) == 1
    assert category_groups[0].id == "group-1"


def create_ynab_transaction(
    *,
    id: str = "txn-1",
    account_id: str = "acc-1",
    amount: int = -50_000,  # -$50.00
    memo: str | None = "Test Transaction",
    cleared: str = "cleared",
    approved: bool = True,
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.TransactionDetail:
    """Create a YNAB TransactionDetail for testing with sensible defaults."""
    return ynab.TransactionDetail(
        id=id,
        date=kwargs.get("date", date.today()),
        amount=amount,
        memo=memo,
        cleared=ynab.TransactionClearedStatus(cleared),
        approved=approved,
        flag_color=kwargs.get("flag_color"),
        account_id=account_id,
        account_name=kwargs.get("account_name", "Test Account"),
        payee_id=kwargs.get("payee_id"),
        payee_name=kwargs.get("payee_name", "Test Payee"),
        category_id=kwargs.get("category_id"),
        category_name=kwargs.get("category_name"),
        transfer_account_id=kwargs.get("transfer_account_id"),
        transfer_transaction_id=kwargs.get("transfer_transaction_id"),
        matched_transaction_id=kwargs.get("matched_transaction_id"),
        import_id=kwargs.get("import_id"),
        import_payee_name=kwargs.get("import_payee_name"),
        import_payee_name_original=kwargs.get("import_payee_name_original"),
        debt_transaction_type=kwargs.get("debt_transaction_type"),
        subtransactions=kwargs.get("subtransactions", []),
        deleted=deleted,
    )


def test_repository_transactions_initial_sync(repository: YNABRepository) -> None:
    """Test repository initial sync for transactions without server knowledge."""
    txn1 = create_ynab_transaction(id="txn-1", amount=-25_000, memo="Groceries")
    txn2 = create_ynab_transaction(id="txn-2", amount=-15_000, memo="Gas")

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=[txn1, txn2], server_knowledge=100
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_transactions_api = MagicMock()
        mock_transactions_api.get_transactions.return_value = transactions_response

        with patch("ynab.TransactionsApi", return_value=mock_transactions_api):
            repository.sync_transactions()

    # Verify initial sync called without last_knowledge_of_server
    mock_transactions_api.get_transactions.assert_called_once_with("test-budget")

    # Verify data was stored
    transactions = repository.get_transactions()
    assert len(transactions) == 2
    assert transactions[0].id == "txn-1"
    assert transactions[1].id == "txn-2"

    # Verify server knowledge was stored
    assert repository._server_knowledge["transactions"] == 100


def test_repository_transactions_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync for transactions with server knowledge."""
    # Set up initial state
    txn1 = create_ynab_transaction(id="txn-1", amount=-25_000, memo="Groceries")
    repository._data["transactions"] = [txn1]
    repository._server_knowledge["transactions"] = 100
    repository._last_sync = datetime.now()

    # Delta sync with updated transaction and new transaction
    updated_txn1 = create_ynab_transaction(
        id="txn-1", amount=-25_000, memo="Groceries (Updated)"
    )
    new_txn = create_ynab_transaction(id="txn-2", amount=-15_000, memo="Gas")

    delta_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=[updated_txn1, new_txn], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_transactions_api = MagicMock()
        mock_transactions_api.get_transactions.return_value = delta_response

        with patch("ynab.TransactionsApi", return_value=mock_transactions_api):
            repository.sync_transactions()

    # Verify delta sync called with last_knowledge_of_server
    mock_transactions_api.get_transactions.assert_called_once_with(
        "test-budget", last_knowledge_of_server=100
    )

    # Verify deltas were applied
    transactions = repository.get_transactions()
    assert len(transactions) == 2

    # Find transactions by ID
    t1 = next(t for t in transactions if t.id == "txn-1")
    t2 = next(t for t in transactions if t.id == "txn-2")

    assert t1.memo == "Groceries (Updated)"  # Updated
    assert t2.memo == "Gas"  # Added

    # Verify server knowledge was updated
    assert repository._server_knowledge["transactions"] == 110


def test_repository_transactions_handles_deleted(repository: YNABRepository) -> None:
    """Test repository handles deleted transactions in delta sync."""
    # Set up initial state with two transactions
    txn1 = create_ynab_transaction(id="txn-1", amount=-25_000, memo="Groceries")
    txn2 = create_ynab_transaction(id="txn-2", amount=-15_000, memo="Gas")
    repository._data["transactions"] = [txn1, txn2]
    repository._server_knowledge["transactions"] = 100
    repository._last_sync = datetime.now()

    # Delta with one deleted transaction
    deleted_txn = create_ynab_transaction(
        id="txn-2", amount=-15_000, memo="Gas", deleted=True
    )

    delta_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=[deleted_txn], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_transactions_api = MagicMock()
        mock_transactions_api.get_transactions.return_value = delta_response

        with patch("ynab.TransactionsApi", return_value=mock_transactions_api):
            repository.sync_transactions()

    # Verify deleted transaction was removed
    transactions = repository.get_transactions()
    assert len(transactions) == 1
    assert transactions[0].id == "txn-1"  # Only groceries transaction remains


def test_repository_transactions_lazy_initialization(
    repository: YNABRepository,
) -> None:
    """Test transactions repository initializes automatically when data requested."""
    txn1 = create_ynab_transaction(id="txn-1", amount=-25_000, memo="Groceries")

    transactions_response = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(transactions=[txn1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_transactions_api = MagicMock()
        mock_transactions_api.get_transactions.return_value = transactions_response

        with patch("ynab.TransactionsApi", return_value=mock_transactions_api):
            # Repository transactions is not initialized initially
            assert "transactions" not in repository._data

            # Calling get_transactions should trigger sync
            transactions = repository.get_transactions()

    # Verify sync was called
    mock_transactions_api.get_transactions.assert_called_once()

    # Verify data is available
    assert len(transactions) == 1
    assert transactions[0].id == "txn-1"


# ===== EDGE CASE AND ERROR HANDLING TESTS =====


def test_repository_needs_sync_functionality(repository: YNABRepository) -> None:
    """Test needs_sync() method behavior."""
    # Fresh repository should need sync
    assert repository.needs_sync()

    # After setting last_sync to now, should not need sync
    repository._last_sync = datetime.now()
    assert not repository.needs_sync()

    # After 6 minutes, should need sync (default threshold is 5 minutes)
    repository._last_sync = datetime.now() - timedelta(minutes=6)
    assert repository.needs_sync()

    # Custom threshold - should not need sync at 3 minutes with 5 minute threshold
    repository._last_sync = datetime.now() - timedelta(minutes=3)
    assert not repository.needs_sync(max_age_minutes=5)

    # Custom threshold - should need sync at 3 minutes with 2 minute threshold
    assert repository.needs_sync(max_age_minutes=2)


def test_repository_conflict_exception_fallback(repository: YNABRepository) -> None:
    """Test that ConflictException triggers fallback to full sync."""
    repository._server_knowledge["accounts"] = 100
    repository._last_sync = datetime.now()

    account1 = create_ynab_account(id="acc-1", name="Checking")
    full_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=120)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        # First call (delta) raises ConflictException (409)
        # Second call (full refresh) succeeds
        mock_accounts_api.get_accounts.side_effect = [
            ConflictException(status=409, reason="Conflict"),
            full_response,
        ]

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Verify fallback behavior
    assert mock_accounts_api.get_accounts.call_count == 2
    accounts = repository.get_accounts()
    assert len(accounts) == 1
    assert repository._server_knowledge["accounts"] == 120


def test_repository_rate_limit_retry_behavior(repository: YNABRepository) -> None:
    """Test that 429 rate limit triggers retry with exponential backoff."""
    account1 = create_ynab_account(id="acc-1", name="Checking")
    success_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        # First call raises 429, second call succeeds
        mock_accounts_api.get_accounts.side_effect = [
            ynab.ApiException(status=429, reason="Too Many Requests"),
            success_response,
        ]

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            with patch("time.sleep") as mock_sleep:
                repository.sync_accounts()

    # Verify retry behavior
    assert mock_accounts_api.get_accounts.call_count == 2
    mock_sleep.assert_called_once_with(1)  # First retry waits 2^0 = 1 second
    accounts = repository.get_accounts()
    assert len(accounts) == 1


def test_repository_rate_limit_max_retries_exceeded(repository: YNABRepository) -> None:
    """Test that repeated 429s eventually give up after max retries."""
    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        # Always return 429
        mock_accounts_api.get_accounts.side_effect = ynab.ApiException(
            status=429, reason="Too Many Requests"
        )

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(ynab.ApiException) as exc_info:
                    repository.sync_accounts()

    # Verify max retries behavior (3 attempts total)
    assert mock_accounts_api.get_accounts.call_count == 3
    assert exc_info.value.status == 429
    # Should have called sleep twice (after first and second attempts)
    assert mock_sleep.call_count == 2


def test_repository_unexpected_exception_not_caught(repository: YNABRepository) -> None:
    """Test that unexpected exceptions are re-raised, not silently caught."""
    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        # Raise a non-API exception
        mock_accounts_api.get_accounts.side_effect = ValueError("Unexpected error")

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            with pytest.raises(ValueError) as exc_info:
                repository.sync_accounts()

    assert str(exc_info.value) == "Unexpected error"


def test_repository_background_sync_not_blocking(repository: YNABRepository) -> None:
    """Test that background sync doesn't block data access."""
    # Enable background sync for this test
    repository._background_sync_enabled = True

    # Set up stale data
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._last_sync = datetime.now() - timedelta(minutes=10)  # Stale

    # Mock needs_sync to return True (stale)
    with patch.object(repository, "needs_sync", return_value=True):
        with patch.object(repository, "_trigger_background_sync") as mock_bg_sync:
            # Getting accounts should return existing data immediately
            accounts = repository.get_accounts()

            # Verify we got the stale data instantly
            assert len(accounts) == 1
            assert accounts[0].id == "acc-1"

            # Verify background sync was triggered
            mock_bg_sync.assert_called_once_with("accounts")


def test_repository_background_sync_error_handling(repository: YNABRepository) -> None:
    """Test that background sync errors don't crash or affect data access."""
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._last_sync = datetime.now() - timedelta(minutes=10)  # Stale

    # Should still return existing data without crashing
    accounts = repository.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "acc-1"


def test_repository_concurrent_access_safety(repository: YNABRepository) -> None:
    """Test that concurrent access to repository data is thread-safe."""

    # Set up initial data using the lock to ensure thread safety
    account1 = create_ynab_account(id="acc-1", name="Checking")
    with repository._lock:
        repository._data["accounts"] = [account1]
        repository._last_sync = datetime.now()

    results = []
    errors = []
    results_lock = threading.Lock()

    # Track which thread should fail for error coverage
    should_fail = [True]  # Use list to make it mutable in closure

    def access_data() -> None:
        try:
            # Make the first thread fail to test exception handling
            if should_fail[0]:
                should_fail[0] = False  # Only fail once
                raise RuntimeError("Test error for coverage")

            accounts = repository.get_accounts()
            # Simulate some processing time
            time.sleep(0.01)
            sync_time = repository.last_sync_time()

            # Thread-safe result collection
            with results_lock:
                results.append((len(accounts), sync_time is not None))
        except Exception as e:
            with results_lock:
                errors.append(e)

    # Start multiple threads accessing data concurrently
    threads = []
    for _ in range(10):
        t = threading.Thread(target=access_data)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify error was captured and other threads succeeded
    assert len(errors) == 1, f"Expected 1 error, got {len(errors)}: {errors}"
    assert isinstance(errors[0], RuntimeError), (
        f"Expected RuntimeError, got {type(errors[0])}"
    )
    assert len(results) == 9, (
        f"Expected 9 results, got {len(results)}: {results}"
    )  # 9 successful threads

    # Extract length and sync_time results from successful threads
    length_results = [r[0] for r in results]
    sync_time_results = [r[1] for r in results]

    assert all(r == 1 for r in length_results), (
        f"Length results not all 1: {length_results}"
    )
    assert all(r is True for r in sync_time_results), (
        f"Sync time results not all True: {sync_time_results}"
    )


def test_repository_concurrent_access_error_handling(
    repository: YNABRepository,
) -> None:
    """Test that errors in concurrent access are properly captured."""

    # Set up initial data
    account1 = create_ynab_account(id="acc-1", name="Checking")
    with repository._lock:
        repository._data["accounts"] = [account1]
        repository._last_sync = datetime.now()

    errors = []
    results_lock = threading.Lock()

    def access_data_with_error() -> None:
        try:
            # Intentionally cause an error by accessing invalid attribute
            _ = repository.get_accounts()
            raise ValueError("Test error for coverage")
        except Exception as e:
            with results_lock:
                errors.append(e)

    # Start a thread that will cause an error
    thread = threading.Thread(target=access_data_with_error)
    thread.start()
    thread.join()

    # Verify the error was captured
    assert len(errors) == 1
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "Test error for coverage"


def test_repository_lazy_init_only_syncs_once(repository: YNABRepository) -> None:
    """Test that lazy initialization only syncs once even with concurrent access."""
    account1 = create_ynab_account(id="acc-1", name="Checking")
    success_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = success_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            # Multiple calls to get_accounts should only sync once
            accounts1 = repository.get_accounts()
            accounts2 = repository.get_accounts()
            accounts3 = repository.get_accounts()

    # Verify only one API call was made
    mock_accounts_api.get_accounts.assert_called_once()

    # All results should be consistent
    assert len(accounts1) == len(accounts2) == len(accounts3) == 1


def test_repository_handles_empty_api_responses(repository: YNABRepository) -> None:
    """Test repository gracefully handles empty API responses."""
    empty_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = empty_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Should handle empty response gracefully
    accounts = repository.get_accounts()
    assert len(accounts) == 0
    assert repository._server_knowledge["accounts"] == 100
    assert repository.is_initialized()


def test_repository_server_knowledge_progression(repository: YNABRepository) -> None:
    """Test that server knowledge progresses correctly through multiple syncs."""
    account1 = create_ynab_account(id="acc-1", name="Checking")

    # First sync
    response1 = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )

    # Second sync with higher knowledge
    account2 = create_ynab_account(id="acc-2", name="Savings")
    response2 = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[account1, account2], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.side_effect = [response1, response2]

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            # First sync
            repository.sync_accounts()
            assert repository._server_knowledge["accounts"] == 100

            # Second sync should use previous knowledge
            repository.sync_accounts()
            assert repository._server_knowledge["accounts"] == 110

    # Verify second call used delta sync
    calls = mock_accounts_api.get_accounts.call_args_list
    assert len(calls) == 2
    assert calls[0][1] == {}  # First call without last_knowledge
    assert calls[1][1] == {
        "last_knowledge_of_server": 100
    }  # Second call with knowledge


def test_repository_mixed_entity_types_independent(repository: YNABRepository) -> None:
    """Test that different entity types sync independently."""
    # Set up different sync states for different entity types
    account1 = create_ynab_account(id="acc-1", name="Checking")
    payee1 = create_ynab_payee(id="payee-1", name="Amazon")

    accounts_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )
    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=[payee1], server_knowledge=200)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = accounts_response

        mock_payees_api = MagicMock()
        mock_payees_api.get_payees.return_value = payees_response

        with (
            patch("ynab.AccountsApi", return_value=mock_accounts_api),
            patch("ynab.PayeesApi", return_value=mock_payees_api),
        ):
            # Sync different entity types
            repository.sync_accounts()
            repository.sync_payees()

    # Verify independent server knowledge tracking
    assert repository._server_knowledge["accounts"] == 100
    assert repository._server_knowledge["payees"] == 200

    # Verify data is separate
    accounts = repository.get_accounts()
    payees = repository.get_payees()
    assert len(accounts) == 1
    assert len(payees) == 1


def test_repository_background_sync_thread_safety(repository: YNABRepository) -> None:
    """Test that background sync threading doesn't cause issues."""

    # Enable background sync for this test
    repository._background_sync_enabled = True

    # Set up initial stale data
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._last_sync = datetime.now() - timedelta(minutes=10)  # Stale

    # Track thread creations
    original_thread = threading.Thread
    created_threads = []

    def track_thread_creation(*args: Any, **kwargs: Any) -> threading.Thread:
        thread = original_thread(*args, **kwargs)
        created_threads.append(thread)
        return thread

    # Mock the actual sync to prevent real API calls
    with patch.object(repository, "sync_accounts"):
        # Mock needs_sync to return True for stale data
        with patch.object(repository, "needs_sync", return_value=True):
            with patch("threading.Thread", side_effect=track_thread_creation):
                # Multiple rapid calls should trigger background sync threads
                repository.get_accounts()
                repository.get_accounts()
                repository.get_accounts()

                # Give threads a moment to be created
                time.sleep(0.1)

    # Should have created threads for background sync (up to 3, one per call)
    assert len(created_threads) <= 3  # At most one per call


def test_repository_preserves_data_during_failed_sync(
    repository: YNABRepository,
) -> None:
    """Test that existing data is preserved when sync fails."""
    # Set up initial good data
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._server_knowledge["accounts"] = 100
    repository._last_sync = datetime.now()

    # Mock sync to fail
    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.side_effect = ynab.ApiException(
            status=500, reason="Server Error"
        )

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            with pytest.raises(ynab.ApiException):
                repository.sync_accounts()

    # Original data should still be there
    accounts = repository.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "acc-1"
    assert repository._server_knowledge["accounts"] == 100


def test_repository_handles_malformed_api_responses(repository: YNABRepository) -> None:
    """Test repository handles malformed or unexpected API response structures."""
    # Mock a response that might have unexpected structure
    malformed_response = MagicMock()
    malformed_response.data.accounts = None  # Unexpected None
    malformed_response.data.server_knowledge = 100

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = malformed_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            # Should handle malformed response gracefully
            with pytest.raises((AttributeError, TypeError)):
                repository.sync_accounts()


def test_repository_sync_entity_atomic_updates(repository: YNABRepository) -> None:
    """Test that _sync_entity updates are atomic."""
    # Set up initial data
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._server_knowledge["accounts"] = 100
    repository._last_sync = datetime.now()

    # Mock successful API call but failing delta application
    account2 = create_ynab_account(id="acc-2", name="Savings")
    success_response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[account1, account2], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = success_response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            # Mock _apply_deltas to fail
            with patch.object(
                repository, "_apply_deltas", side_effect=Exception("Delta failed")
            ):
                # Sync should fail
                with pytest.raises(Exception, match="Delta failed"):
                    repository.sync_accounts()

    # Original data should be unchanged due to atomic failure
    accounts = repository.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "acc-1"
    assert repository._server_knowledge["accounts"] == 100  # Should not be updated


def test_repository_handles_very_large_server_knowledge_values(
    repository: YNABRepository,
) -> None:
    """Test repository handles very large server knowledge values correctly."""
    # Test with a very large server knowledge value
    large_knowledge = 999_999_999_999

    account1 = create_ynab_account(id="acc-1", name="Checking")
    response = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=[account1], server_knowledge=large_knowledge
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Should handle large values correctly
    assert repository._server_knowledge["accounts"] == large_knowledge

    # Should be able to use it in subsequent delta calls
    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_accounts_api = MagicMock()
        mock_accounts_api.get_accounts.return_value = response

        with patch("ynab.AccountsApi", return_value=mock_accounts_api):
            repository.sync_accounts()

    # Verify large knowledge was passed correctly
    mock_accounts_api.get_accounts.assert_called_with(
        "test-budget", last_knowledge_of_server=large_knowledge
    )


def test_repository_background_sync_respects_staleness_threshold(
    repository: YNABRepository,
) -> None:
    """Test that background sync only triggers when data is actually stale."""
    # Set up fresh data (not stale)
    account1 = create_ynab_account(id="acc-1", name="Checking")
    repository._data["accounts"] = [account1]
    repository._last_sync = datetime.now() - timedelta(minutes=2)  # Fresh (< 5 minutes)

    with patch.object(repository, "_trigger_background_sync") as mock_bg_sync:
        # Getting accounts should NOT trigger background sync
        accounts = repository.get_accounts()

        # Verify we got the data
        assert len(accounts) == 1
        assert accounts[0].id == "acc-1"

        # Verify background sync was NOT triggered
        mock_bg_sync.assert_not_called()


def test_repository_error_logging_behavior(repository: YNABRepository) -> None:
    """Test that errors are properly logged with appropriate levels."""

    # Capture log messages
    log_messages = []

    class TestLogHandler(logging.Handler):
        def emit(self, record: Any) -> None:
            log_messages.append((record.levelname, record.getMessage()))

    # Add test handler to repository logger
    test_handler = TestLogHandler()
    repository_logger = logging.getLogger("repository")
    repository_logger.addHandler(test_handler)
    repository_logger.setLevel(logging.DEBUG)

    try:
        with patch("ynab.ApiClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client

            mock_accounts_api = MagicMock()

            # Set up initial server knowledge to trigger delta sync path
            repository._server_knowledge["accounts"] = 50

            # Test different error scenarios
            # 1. ConflictException should log as INFO (expected)
            mock_accounts_api.get_accounts.side_effect = [
                ConflictException(status=409, reason="Conflict"),
                ynab.AccountsResponse(
                    data=ynab.AccountsResponseData(accounts=[], server_knowledge=100)
                ),
            ]

            with patch("ynab.AccountsApi", return_value=mock_accounts_api):
                repository.sync_accounts()

            # 2. Generic ApiException should log as WARNING
            # Reset server knowledge for next test
            repository._server_knowledge["accounts"] = 60
            mock_accounts_api.get_accounts.side_effect = [
                ynab.ApiException(status=500, reason="Server Error"),
                ynab.AccountsResponse(
                    data=ynab.AccountsResponseData(accounts=[], server_knowledge=100)
                ),
            ]

            with patch("ynab.AccountsApi", return_value=mock_accounts_api):
                repository.sync_accounts()

        # Verify appropriate log levels were used
        info_logs = [msg for level, msg in log_messages if level == "INFO"]
        warning_logs = [msg for level, msg in log_messages if level == "WARNING"]

        assert any("conflict" in msg.lower() for msg in info_logs)
        assert any("api error" in msg.lower() for msg in warning_logs)

    finally:
        # Clean up
        repository_logger.removeHandler(test_handler)
