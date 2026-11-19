"""
Test how the repository keeps YNAB's server knowledge for each entity type.
"""

from unittest.mock import MagicMock, patch

import ynab
from conftest import (
    create_ynab_account,
    create_ynab_payee,
)
from ids import uid

from you_need_an_mcp.repository import YNABRepository


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
    assert repository.server_knowledge("accounts") == 100
    assert repository.is_initialized()


def test_repository_server_knowledge_progression(repository: YNABRepository) -> None:
    """Test that server knowledge progresses correctly through multiple syncs."""
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")

    # First sync
    response1 = ynab.AccountsResponse(
        data=ynab.AccountsResponseData(accounts=[account1], server_knowledge=100)
    )

    # Second sync with higher knowledge
    account2 = create_ynab_account(id=uid("acc-2"), name="Savings")
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
            assert repository.server_knowledge("accounts") == 100

            # Second sync should use previous knowledge
            repository.sync_accounts()
            assert repository.server_knowledge("accounts") == 110

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
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    payee1 = create_ynab_payee(id=uid("payee-1"), name="Amazon")

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
    assert repository.server_knowledge("accounts") == 100
    assert repository.server_knowledge("payees") == 200

    # Verify data is separate
    accounts = repository.get_accounts()
    payees = repository.get_payees()
    assert len(accounts) == 1
    assert len(payees) == 1


def test_repository_handles_very_large_server_knowledge_values(
    repository: YNABRepository,
) -> None:
    """Test repository handles very large server knowledge values correctly."""
    # Test with a very large server knowledge value
    large_knowledge = 999_999_999_999

    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
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
    assert repository.server_knowledge("accounts") == large_knowledge

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
