"""
YNAB Repository with differential sync.

Provides local-first access to YNAB data with background synchronization.
"""

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import ynab
from ynab.exceptions import ApiException, ConflictException

logger = logging.getLogger(__name__)

# YNAB answers in well under a second.  A request that has not finished in
# this long is stuck, and a tool that waits on it forever hangs its client.
REQUEST_TIMEOUT_SECONDS = 30.0


class TimeoutApiClient(ynab.ApiClient):
    """A YNAB API client with a default request timeout.

    The generated SDK sends requests with no timeout unless each call passes
    one, so this applies one to every call that does not.
    """

    def call_api(
        self,
        method: str,
        url: str,
        header_params: dict[str, str] | None = None,
        body: Any = None,
        post_params: list[tuple[str, Any]] | None = None,
        _request_timeout: Any = None,
    ) -> ynab.rest.RESTResponse:
        return super().call_api(
            method,
            url,
            header_params=header_params,
            body=body,
            post_params=post_params,
            _request_timeout=_request_timeout or REQUEST_TIMEOUT_SECONDS,
        )


class YNABRepository:
    """Local repository for YNAB data with background differential sync."""

    def __init__(self, plan_id: str, access_token: str):
        self.plan_id = plan_id
        self.configuration = ynab.Configuration(access_token=access_token)

        # In-memory storage - generic dict for different entity types
        self._data: dict[str, list[Any]] = {}
        self._server_knowledge: dict[str, int] = {}
        self._lock = threading.RLock()
        self._last_sync: datetime | None = None
        self._stale: set[str] = set()

        # Testing flag to disable background sync
        self._background_sync_enabled = True

    def get_accounts(self) -> list[ynab.Account]:
        """Get all accounts from local repository."""
        return self._get_entity("accounts", self.sync_accounts)

    def get_payees(self) -> list[ynab.Payee]:
        """Get all payees from local repository."""
        return self._get_entity("payees", self.sync_payees)

    def get_category_groups(self) -> list[ynab.CategoryGroupWithCategories]:
        """Get all category groups from local repository."""
        return self._get_entity("category_groups", self.sync_category_groups)

    def get_transactions(self) -> list[ynab.TransactionDetail]:
        """Get all transactions from local repository."""
        return self._get_entity("transactions", self.sync_transactions)

    def _get_entity(self, entity_type: str, sync: Callable[[], None]) -> list[Any]:
        """Serve an entity list from memory, syncing it first when it must be.

        The first read syncs in the foreground, because there is nothing to
        serve yet.  A read after one of our own writes also syncs in the
        foreground, so that the caller sees the change it just made.  A read
        of data that is only old syncs in the background and serves what is
        already here.
        """
        with self._lock:
            if entity_type not in self._data:
                logger.info(f"No {entity_type} data - performing initial sync")
                sync()
            elif entity_type in self._stale:
                logger.info(f"{entity_type} changed by a write - syncing now")
                sync()
            elif self.needs_sync():
                logger.info(f"{entity_type} data is stale - triggering background sync")
                self._trigger_background_sync(entity_type)

            return self._data.get(entity_type, [])

    def mark_stale(self, *entity_types: str) -> None:
        """Record that a write changed these entities on the server.

        The next read of each one runs a delta sync before it answers.  The
        delta sync starts from the server knowledge we already hold, so it
        fetches only what changed rather than the whole plan.
        """
        with self._lock:
            self._stale.update(entity_types)

    @contextmanager
    def api(self) -> Iterator[ynab.ApiClient]:
        """Open a YNAB API client that gives up on a request after a timeout."""
        with TimeoutApiClient(self.configuration) as api_client:
            yield api_client

    def sync_accounts(self) -> None:
        """Sync accounts with YNAB API using differential sync."""
        self._sync_entity("accounts", self._sync_accounts_from_api)

    def sync_payees(self) -> None:
        """Sync payees with YNAB API using differential sync."""
        self._sync_entity("payees", self._sync_payees_from_api)

    def sync_category_groups(self) -> None:
        """Sync category groups with YNAB API using differential sync."""
        self._sync_entity("category_groups", self._sync_category_groups_from_api)

    def sync_transactions(self) -> None:
        """Sync transactions with YNAB API using differential sync."""
        self._sync_entity("transactions", self._sync_transactions_from_api)

    def _sync_accounts_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.Account], int]:
        """Fetch accounts from YNAB API with optional server knowledge."""
        with self.api() as api_client:
            api = ynab.AccountsApi(api_client)

            def fetch(knowledge: int | None) -> tuple[list[ynab.Account], int]:
                if knowledge is None:
                    response = api.get_accounts(self.plan_id)
                else:
                    response = api.get_accounts(
                        self.plan_id, last_knowledge_of_server=knowledge
                    )
                return list(response.data.accounts), response.data.server_knowledge

            return self._fetch_entities("accounts", last_knowledge, fetch)

    def _sync_payees_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.Payee], int]:
        """Fetch payees from YNAB API with optional server knowledge."""
        with self.api() as api_client:
            api = ynab.PayeesApi(api_client)

            def fetch(knowledge: int | None) -> tuple[list[ynab.Payee], int]:
                if knowledge is None:
                    response = api.get_payees(self.plan_id)
                else:
                    response = api.get_payees(
                        self.plan_id, last_knowledge_of_server=knowledge
                    )
                return list(response.data.payees), response.data.server_knowledge

            return self._fetch_entities("payees", last_knowledge, fetch)

    def _sync_category_groups_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.CategoryGroupWithCategories], int]:
        """Fetch category groups from YNAB API with optional server knowledge."""
        with self.api() as api_client:
            api = ynab.CategoriesApi(api_client)

            def fetch(
                knowledge: int | None,
            ) -> tuple[list[ynab.CategoryGroupWithCategories], int]:
                if knowledge is None:
                    response = api.get_categories(self.plan_id)
                else:
                    response = api.get_categories(
                        self.plan_id, last_knowledge_of_server=knowledge
                    )
                return (
                    list(response.data.category_groups),
                    response.data.server_knowledge,
                )

            return self._fetch_entities("category groups", last_knowledge, fetch)

    def _sync_transactions_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.TransactionDetail], int]:
        """Fetch transactions from YNAB API with optional server knowledge."""
        with self.api() as api_client:
            api = ynab.TransactionsApi(api_client)

            def fetch(
                knowledge: int | None,
            ) -> tuple[list[ynab.TransactionDetail], int]:
                if knowledge is None:
                    response = api.get_transactions(self.plan_id)
                else:
                    response = api.get_transactions(
                        self.plan_id, last_knowledge_of_server=knowledge
                    )
                return (
                    list(response.data.transactions),
                    response.data.server_knowledge,
                )

            return self._fetch_entities("transactions", last_knowledge, fetch)

    def _fetch_entities[T](
        self,
        entity_name: str,
        last_knowledge: int | None,
        fetch: Callable[[int | None], tuple[list[T], int]],
    ) -> tuple[list[T], int]:
        """Fetch only the changes since last_knowledge, or everything.

        YNAB refuses a delta when our server knowledge is too old, and any
        other failed delta leaves us unsure what changed.  Either way, fetching
        everything again gets us back to a state we can trust.
        """
        if last_knowledge is None:
            return self._handle_api_call_with_retry(lambda: fetch(None))
        try:
            return self._handle_api_call_with_retry(lambda: fetch(last_knowledge))
        except ConflictException as e:
            logger.info(f"Falling back to full {entity_name} sync due to conflict: {e}")
        except ApiException as e:
            logger.warning(f"API error during {entity_name} delta sync: {e}")
        return self._handle_api_call_with_retry(lambda: fetch(None))

    def _sync_entity(
        self, entity_type: str, sync_func: Callable[[int | None], tuple[list[Any], int]]
    ) -> None:
        """Generic sync method for any entity type."""
        with self._lock:
            current_knowledge = self._server_knowledge.get(entity_type, 0)
            last_knowledge = current_knowledge if current_knowledge > 0 else None

            # Fetch from API
            entities, new_knowledge = sync_func(last_knowledge)

            # Apply changes
            if last_knowledge is not None and entity_type in self._data:
                # Apply delta changes
                self._apply_deltas(entity_type, entities)
            else:
                # Full refresh
                self._data[entity_type] = entities

            # Update metadata
            self._server_knowledge[entity_type] = new_knowledge
            self._stale.discard(entity_type)
            self._last_sync = datetime.now()

    def _apply_deltas(self, entity_type: str, delta_entities: list[Any]) -> None:
        """Apply delta changes to an entity list."""
        current_entities = self._data.get(entity_type, [])
        entity_map = {entity.id: entity for entity in current_entities}

        for delta_entity in delta_entities:
            if hasattr(delta_entity, "deleted") and delta_entity.deleted:
                # Remove deleted entity
                entity_map.pop(delta_entity.id, None)
            else:
                # Add new or update existing entity
                entity_map[delta_entity.id] = delta_entity

        # Update the entity list
        self._data[entity_type] = list(entity_map.values())

    def is_initialized(self) -> bool:
        """Check if repository has been initially populated."""
        with self._lock:
            return len(self._data) > 0 or self._last_sync is not None

    def last_sync_time(self) -> datetime | None:
        """Get the last sync time."""
        with self._lock:
            return self._last_sync

    def needs_sync(self, max_age_minutes: int = 5) -> bool:
        """Check if repository needs to be synced based on staleness."""
        with self._lock:
            if self._last_sync is None:
                return True

            age_minutes = (datetime.now() - self._last_sync).total_seconds() / 60
            return age_minutes > max_age_minutes

    def _trigger_background_sync(self, entity_type: str) -> None:
        """Trigger background sync for a specific entity type."""
        if not self._background_sync_enabled:
            return

        sync_method = {
            "accounts": self.sync_accounts,
            "payees": self.sync_payees,
            "category_groups": self.sync_category_groups,
            "transactions": self.sync_transactions,
        }[entity_type]

        sync_thread = threading.Thread(
            target=self._background_sync_entity,
            args=(entity_type, sync_method),
            daemon=True,
            name=f"ynab-sync-{entity_type}",
        )
        sync_thread.start()

    def _background_sync_entity(
        self, entity_type: str, sync_method: Callable[[], None]
    ) -> None:
        """Background sync for a specific entity type with error handling."""
        try:
            logger.info(f"Starting background sync for {entity_type}")
            sync_method()
            logger.info(f"Completed background sync for {entity_type}")
        except Exception as e:
            logger.error(f"Background sync failed for {entity_type}: {e}")
            # Continue serving stale data on error

    def _handle_api_call_with_retry[T](
        self, api_call: Callable[[], T], max_retries: int = 3
    ) -> T:
        """Call the YNAB API, backing off and retrying when rate limited.

        YNAB allows 200 requests an hour.  Any other error, including the
        conflict that tells a delta sync to start over, goes to the caller.
        """
        attempt = 0
        while True:
            try:
                return api_call()
            except ApiException as e:
                if e.status != 429:
                    logger.error(f"API error {e.status}: {e}")
                    raise
                if attempt >= max_retries - 1:
                    logger.error("Max retries exceeded for rate limiting")
                    raise
                wait_time = 2**attempt
                logger.warning(
                    f"Rate limited - waiting {wait_time}s (retry {attempt + 1})"
                )
                time.sleep(wait_time)
                attempt += 1


def plan_repository() -> YNABRepository:
    """Build the repository for the plan this server is configured for.

    Tools receive it through FastMCP's Shared dependency, so the server builds
    one repository for its whole lifetime and every tool reads the same cache.
    """
    return YNABRepository(
        plan_id=os.environ["YNAB_PLAN"],
        access_token=os.environ["YNAB_ACCESS_TOKEN"],
    )
