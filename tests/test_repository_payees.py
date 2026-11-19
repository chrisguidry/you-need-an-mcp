"""
Test how the repository syncs payees from YNAB, in full and by delta.
"""

from unittest.mock import MagicMock, create_autospec, patch

import ynab
from conftest import (
    create_ynab_payee,
)
from ids import uid

from you_need_an_mcp.repository import YNABRepository


def seed_payees(
    repository: YNABRepository,
    payees: list[ynab.Payee],
    server_knowledge: int = 100,
) -> None:
    """Load payees into a repository the way a sync from YNAB does."""
    api = create_autospec(ynab.PayeesApi, instance=True)
    api.get_payees.return_value = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=payees, server_knowledge=server_knowledge)
    )
    with patch("ynab.PayeesApi", return_value=api):
        repository.sync_payees()


def test_repository_payees_initial_sync(repository: YNABRepository) -> None:
    """Test repository initial sync for payees without server knowledge."""
    payee1 = create_ynab_payee(id=uid("payee-1"), name="Amazon")
    payee2 = create_ynab_payee(id=uid("payee-2"), name="Starbucks")

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
    assert payees[0].id == uid("payee-1")
    assert payees[1].id == uid("payee-2")

    # Verify server knowledge was stored
    assert repository.server_knowledge("payees") == 100


def test_repository_payees_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync for payees with server knowledge."""
    # Set up initial state
    payee1 = create_ynab_payee(id=uid("payee-1"), name="Amazon")
    seed_payees(repository, [payee1])

    # Delta sync with updated payee and new payee
    updated_payee1 = create_ynab_payee(id=uid("payee-1"), name="Amazon.com")
    new_payee = create_ynab_payee(id=uid("payee-2"), name="Target")

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
    p1 = next(p for p in payees if p.id == uid("payee-1"))
    p2 = next(p for p in payees if p.id == uid("payee-2"))

    assert p1.name == "Amazon.com"  # Updated
    assert p2.name == "Target"  # Added

    # Verify server knowledge was updated
    assert repository.server_knowledge("payees") == 110


def test_repository_payees_handles_deleted(repository: YNABRepository) -> None:
    """Test repository handles deleted payees in delta sync."""
    # Set up initial state with two payees
    payee1 = create_ynab_payee(id=uid("payee-1"), name="Amazon")
    payee2 = create_ynab_payee(id=uid("payee-2"), name="Old Store")
    seed_payees(repository, [payee1, payee2])

    # Delta with one deleted payee
    deleted_payee = create_ynab_payee(id=uid("payee-2"), name="Old Store", deleted=True)

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
    assert payees[0].id == uid("payee-1")  # Only Amazon remains


def test_repository_payees_lazy_initialization(repository: YNABRepository) -> None:
    """Test payees repository initializes automatically when data is requested."""
    payee1 = create_ynab_payee(id=uid("payee-1"), name="Amazon")

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
            assert not repository.is_initialized()

            # Calling get_payees should trigger sync
            payees = repository.get_payees()

    # Verify sync was called
    mock_payees_api.get_payees.assert_called_once()

    # Verify data is available
    assert len(payees) == 1
    assert payees[0].id == uid("payee-1")
