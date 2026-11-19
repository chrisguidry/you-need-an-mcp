"""
Test how the repository handles YNAB's errors: conflicts, rate limits, and
failed syncs.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
import ynab
from conftest import (
    create_ynab_account,
    seed_accounts,
)
from ids import uid
from ynab.exceptions import ConflictException

from you_need_an_mcp.repository import YNABRepository
from you_need_an_mcp.ynab_errors import api_status


def test_repository_conflict_exception_fallback(repository: YNABRepository) -> None:
    """Test that ConflictException triggers fallback to full sync."""
    seed_accounts(repository, [])

    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
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
    assert repository.server_knowledge("accounts") == 120


def test_repository_rate_limit_retry_behavior(repository: YNABRepository) -> None:
    """Test that 429 rate limit triggers retry with exponential backoff."""
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
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
    assert api_status(exc_info.value) == 429
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


def test_repository_preserves_data_during_failed_sync(
    repository: YNABRepository,
) -> None:
    """Test that existing data is preserved when sync fails."""
    # Set up initial good data
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])

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
    assert accounts[0].id == uid("acc-1")
    assert repository.server_knowledge("accounts") == 100


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
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])

    # Mock successful API call but failing delta application
    account2 = create_ynab_account(id=uid("acc-2"), name="Savings")
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
    assert accounts[0].id == uid("acc-1")
    assert repository.server_knowledge("accounts") == 100  # Should not be updated


def test_repository_error_logging_behavior(repository: YNABRepository) -> None:
    """Test that errors are properly logged with appropriate levels."""

    # Capture log messages
    log_messages: list[tuple[str, str]] = []

    class TestLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            log_messages.append((record.levelname, record.getMessage()))

    # Add test handler to repository logger
    test_handler = TestLogHandler()
    repository_logger = logging.getLogger("you_need_an_mcp.repository")
    repository_logger.addHandler(test_handler)
    repository_logger.setLevel(logging.DEBUG)

    try:
        with patch("ynab.ApiClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client

            mock_accounts_api = MagicMock()

            # Set up initial server knowledge to trigger delta sync path
            seed_accounts(repository, [], 50)

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
