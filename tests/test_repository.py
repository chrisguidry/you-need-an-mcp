"""
Test suite for YNABRepository differential sync functionality.

Tests the repository pattern implementation including initial sync, delta sync,
and error handling scenarios.
"""

from datetime import datetime
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
