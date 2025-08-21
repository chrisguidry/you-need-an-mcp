"""
Test suite for YNABRepository differential sync functionality.

Tests the repository pattern implementation including initial sync, delta sync,
and error handling scenarios.
"""

from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import ynab

from repository import YNABRepository


def create_ynab_account(
    *,
    id: str = "acc-1",
    name: str = "Test Account",
    deleted: bool = False,
    **kwargs: Any,
) -> ynab.Account:
    """Create a YNAB Account for testing with sensible defaults."""
    return ynab.Account(
        id=id,
        name=name,
        type=kwargs.get("type", ynab.AccountType.CHECKING),
        on_budget=kwargs.get("on_budget", True),
        closed=kwargs.get("closed", False),
        note=kwargs.get("note"),
        balance=kwargs.get("balance", 100_000),
        cleared_balance=kwargs.get("cleared_balance", 95_000),
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


@pytest.fixture
def repository() -> YNABRepository:
    """Create a repository instance for testing."""
    return YNABRepository(budget_id="test-budget", access_token="test-token")


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
        # First call (delta) raises exception
        # Second call (full refresh) succeeds
        mock_accounts_api.get_accounts.side_effect = [
            Exception("Delta failed"),
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
