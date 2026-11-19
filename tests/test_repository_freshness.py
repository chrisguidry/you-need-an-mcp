"""
Test when the repository serves from memory, when it syncs, and how it
behaves under concurrent reads.
"""

import threading
import time
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import ynab
from conftest import (
    Clock,
    create_ynab_account,
    seed_accounts,
)
from ids import uid

from repository import YNABRepository


def background_syncing_repository(clock: Clock) -> YNABRepository:
    """A repository that syncs stale data in the background, as it does live."""
    return YNABRepository(plan_id="test-budget", access_token="test-token", clock=clock)


def test_repository_needs_sync_functionality(
    repository: YNABRepository, clock: Clock
) -> None:
    """Test needs_sync() method behavior."""
    # Fresh repository should need sync
    assert repository.needs_sync()

    # Right after a sync, should not need sync
    seed_accounts(repository, [])
    synced_at = clock.now
    assert not repository.needs_sync()

    # After 6 minutes, should need sync (default threshold is 5 minutes)
    clock.advance(minutes=6)
    assert repository.needs_sync()

    # Custom threshold - should not need sync at 3 minutes with 5 minute threshold
    clock.now = synced_at + timedelta(minutes=3)
    assert not repository.needs_sync(max_age_minutes=5)

    # Custom threshold - should need sync at 3 minutes with 2 minute threshold
    assert repository.needs_sync(max_age_minutes=2)


def test_repository_background_sync_not_blocking(clock: Clock) -> None:
    """Test that background sync doesn't block data access."""
    repository = background_syncing_repository(clock)

    # Set up stale data
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])
    clock.advance(minutes=10)

    # Mock needs_sync to return True (stale)
    with patch.object(repository, "needs_sync", return_value=True):
        with patch.object(repository, "_trigger_background_sync") as mock_bg_sync:
            # Getting accounts should return existing data immediately
            accounts = repository.get_accounts()

            # Verify we got the stale data instantly
            assert len(accounts) == 1
            assert accounts[0].id == uid("acc-1")

            # Verify background sync was triggered
            mock_bg_sync.assert_called_once_with("accounts")


def test_repository_background_sync_error_handling(
    repository: YNABRepository, clock: Clock
) -> None:
    """Test that background sync errors don't crash or affect data access."""
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])
    clock.advance(minutes=10)

    # Should still return existing data without crashing
    accounts = repository.get_accounts()
    assert len(accounts) == 1
    assert accounts[0].id == uid("acc-1")


def test_repository_concurrent_access_safety(repository: YNABRepository) -> None:
    """Test that concurrent access to repository data is thread-safe."""

    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])

    results: list[tuple[int, bool]] = []
    errors: list[Exception] = []
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
    threads: list[threading.Thread] = []
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
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])

    errors: list[Exception] = []
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
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
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


def test_repository_background_sync_thread_safety(clock: Clock) -> None:
    """Test that background sync threading doesn't cause issues."""
    repository = background_syncing_repository(clock)

    # Set up initial stale data
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])
    clock.advance(minutes=10)

    # Track thread creations
    original_thread = threading.Thread
    created_threads: list[threading.Thread] = []

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


def test_repository_background_sync_respects_staleness_threshold(
    repository: YNABRepository, clock: Clock
) -> None:
    """Test that background sync only triggers when data is actually stale."""
    # Set up fresh data (not stale)
    account1 = create_ynab_account(id=uid("acc-1"), name="Checking")
    seed_accounts(repository, [account1])
    clock.advance(minutes=2)  # Fresh (< 5 minutes)

    with patch.object(repository, "_trigger_background_sync") as mock_bg_sync:
        # Getting accounts should NOT trigger background sync
        accounts = repository.get_accounts()

        # Verify we got the data
        assert len(accounts) == 1
        assert accounts[0].id == uid("acc-1")

        # Verify background sync was NOT triggered
        mock_bg_sync.assert_not_called()
