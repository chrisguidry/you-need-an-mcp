"""
Test how the repository syncs transactions from YNAB, in full and by delta.
"""

from unittest.mock import MagicMock, create_autospec, patch

import ynab
from conftest import (
    create_ynab_transaction,
)

from you_need_an_mcp.repository import YNABRepository


def seed_transactions(
    repository: YNABRepository,
    transactions: list[ynab.TransactionDetail],
    server_knowledge: int = 100,
) -> None:
    """Load transactions into a repository the way a sync from YNAB does."""
    api = create_autospec(ynab.TransactionsApi, instance=True)
    api.get_transactions.return_value = ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(
            transactions=transactions, server_knowledge=server_knowledge
        )
    )
    with patch("ynab.TransactionsApi", return_value=api):
        repository.sync_transactions()


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
    assert repository.server_knowledge("transactions") == 100


def test_repository_transactions_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync for transactions with server knowledge."""
    # Set up initial state
    txn1 = create_ynab_transaction(id="txn-1", amount=-25_000, memo="Groceries")
    seed_transactions(repository, [txn1])

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
    assert repository.server_knowledge("transactions") == 110


def test_repository_transactions_handles_deleted(repository: YNABRepository) -> None:
    """Test repository handles deleted transactions in delta sync."""
    # Set up initial state with two transactions
    txn1 = create_ynab_transaction(id="txn-1", amount=-25_000, memo="Groceries")
    txn2 = create_ynab_transaction(id="txn-2", amount=-15_000, memo="Gas")
    seed_transactions(repository, [txn1, txn2])

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
            assert not repository.is_initialized()

            # Calling get_transactions should trigger sync
            transactions = repository.get_transactions()

    # Verify sync was called
    mock_transactions_api.get_transactions.assert_called_once()

    # Verify data is available
    assert len(transactions) == 1
    assert transactions[0].id == "txn-1"
