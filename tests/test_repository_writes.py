"""
Test how the repository serves reads after our own writes, and how it talks to
YNAB.
"""

import threading
from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import ynab
from conftest import create_ynab_account
from ids import uid

from repository import (
    REQUEST_TIMEOUT_SECONDS,
    TimeoutApiClient,
    YNABRepository,
    plan_repository,
)


def accounts_response(
    accounts: list[ynab.Account], server_knowledge: int
) -> ynab.AccountsResponse:
    return ynab.AccountsResponse(
        data=ynab.AccountsResponseData(
            accounts=accounts, server_knowledge=server_knowledge
        )
    )


@pytest.fixture
def accounts_api() -> Generator[MagicMock, None, None]:
    api = MagicMock(spec=ynab.AccountsApi)
    with patch("ynab.AccountsApi", return_value=api):
        yield api


@pytest.fixture
def repository() -> YNABRepository:
    repository = YNABRepository(plan_id="test-plan", access_token="test-token")
    repository._background_sync_enabled = False
    return repository


def test_a_read_after_a_write_runs_a_delta_sync_first(
    repository: YNABRepository, accounts_api: MagicMock
) -> None:
    accounts_api.get_accounts.side_effect = [
        accounts_response([create_ynab_account(name="Checking")], 100),
        accounts_response([create_ynab_account(name="Checking", balance=5_000)], 101),
    ]
    repository.get_accounts()

    repository.mark_stale("accounts")
    accounts = repository.get_accounts()

    assert accounts[0].balance == 5_000
    assert accounts_api.get_accounts.call_args.kwargs == {
        "last_knowledge_of_server": 100
    }


def test_a_read_after_the_delta_sync_uses_memory(
    repository: YNABRepository, accounts_api: MagicMock
) -> None:
    accounts_api.get_accounts.return_value = accounts_response(
        [create_ynab_account()], 100
    )
    repository.get_accounts()
    repository.mark_stale("accounts")
    repository.get_accounts()

    repository.get_accounts()

    assert accounts_api.get_accounts.call_count == 2


def test_marking_one_entity_stale_leaves_the_others(
    repository: YNABRepository, accounts_api: MagicMock
) -> None:
    accounts_api.get_accounts.return_value = accounts_response(
        [create_ynab_account(id=uid("acc-1"))], 100
    )
    repository.get_accounts()

    repository.mark_stale("payees")
    repository.get_accounts()

    assert accounts_api.get_accounts.call_count == 1


def wait_for_background_syncs() -> None:
    syncs = [t for t in threading.enumerate() if t.name.startswith("ynab-sync-")]
    for sync in syncs:
        sync.join(timeout=5)


def test_a_failed_background_sync_keeps_serving_what_is_cached(
    repository: YNABRepository, accounts_api: MagicMock
) -> None:
    accounts_api.get_accounts.side_effect = [
        accounts_response([create_ynab_account(name="Checking")], 100),
        RuntimeError("YNAB is down"),
    ]
    repository.get_accounts()
    repository._background_sync_enabled = True
    repository._last_sync = datetime.now() - timedelta(minutes=10)

    repository.get_accounts()
    wait_for_background_syncs()

    assert [account.name for account in repository.get_accounts()] == ["Checking"]
    assert accounts_api.get_accounts.call_count == 2


@pytest.mark.parametrize(
    ("given", "sent"),
    [(None, REQUEST_TIMEOUT_SECONDS), (5.0, 5.0), ((1.0, 2.0), (1.0, 2.0))],
)
def test_api_client_applies_a_default_timeout(
    given: float | tuple[float, float] | None,
    sent: float | tuple[float, float],
) -> None:
    with (
        patch.object(ynab.ApiClient, "call_api") as call_api,
        TimeoutApiClient(ynab.Configuration(access_token="test")) as client,
    ):
        client.call_api("GET", "https://api.ynab.com/v1/user", _request_timeout=given)

    assert call_api.call_args.kwargs["_request_timeout"] == sent


def test_repository_api_opens_a_timeout_client(repository: YNABRepository) -> None:
    with repository.api() as api_client:
        assert isinstance(api_client, TimeoutApiClient)


def test_plan_repository_uses_the_configured_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YNAB_PLAN", "my-plan")
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "my-token")

    repository = plan_repository()

    assert repository.plan_id == "my-plan"
    assert repository.configuration.access_token == "my-token"
