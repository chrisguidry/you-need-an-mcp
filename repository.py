"""
YNAB Repository with differential sync.

Provides local-first access to YNAB data with background synchronization.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import ynab
from ynab.exceptions import ApiException, ConflictException

logger = logging.getLogger(__name__)


class YNABRepository:
    """Local repository for YNAB data with background differential sync."""

    def __init__(self, budget_id: str, access_token: str):
        self.budget_id = budget_id
        self.configuration = ynab.Configuration(access_token=access_token)

        # In-memory storage - generic dict for different entity types
        self._data: dict[str, list[Any]] = {}
        self._server_knowledge: dict[str, int] = {}
        self._lock = threading.RLock()
        self._last_sync: datetime | None = None

        # Testing flag to disable background sync
        self._background_sync_enabled = True

    def get_accounts(self) -> list[ynab.Account]:
        """Get all accounts from local repository."""
        with self._lock:
            # If no data exists, do synchronous sync (first time)
            if "accounts" not in self._data:
                logger.info("No accounts data - performing initial sync")
                self.sync_accounts()
            # If data exists but is stale, trigger background sync
            elif self.needs_sync():
                logger.info("Accounts data is stale - triggering background sync")
                self._trigger_background_sync("accounts")

            return self._data.get("accounts", [])

    def get_payees(self) -> list[ynab.Payee]:
        """Get all payees from local repository."""
        with self._lock:
            # If no data exists, do synchronous sync (first time)
            if "payees" not in self._data:
                logger.info("No payees data - performing initial sync")
                self.sync_payees()
            # If data exists but is stale, trigger background sync
            elif self.needs_sync():
                logger.info("Payees data is stale - triggering background sync")
                self._trigger_background_sync("payees")

            return self._data.get("payees", [])

    def get_category_groups(self) -> list[ynab.CategoryGroupWithCategories]:
        """Get all category groups from local repository."""
        with self._lock:
            # If no data exists, do synchronous sync (first time)
            if "category_groups" not in self._data:
                logger.info("No category groups data - performing initial sync")
                self.sync_category_groups()
            # If data exists but is stale, trigger background sync
            elif self.needs_sync():
                logger.info(
                    "Category groups data is stale - triggering background sync"
                )
                self._trigger_background_sync("category_groups")

            return self._data.get("category_groups", [])

    def get_transactions(self) -> list[ynab.TransactionDetail]:
        """Get all transactions from local repository."""
        with self._lock:
            # If no data exists, do synchronous sync (first time)
            if "transactions" not in self._data:
                logger.info("No transactions data - performing initial sync")
                self.sync_transactions()
            # If data exists but is stale, trigger background sync
            elif self.needs_sync():
                logger.info("Transactions data is stale - triggering background sync")
                self._trigger_background_sync("transactions")

            return self._data.get("transactions", [])

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
        with ynab.ApiClient(self.configuration) as api_client:
            accounts_api = ynab.AccountsApi(api_client)

            if last_knowledge is not None:
                try:
                    # Try delta sync first
                    response = self._handle_api_call_with_retry(
                        lambda: accounts_api.get_accounts(
                            self.budget_id, last_knowledge_of_server=last_knowledge
                        )
                    )
                except ConflictException as e:
                    # Fall back to full sync on stale knowledge
                    logger.info(
                        f"Falling back to full accounts sync due to conflict: {e}"
                    )
                    response = self._handle_api_call_with_retry(
                        lambda: accounts_api.get_accounts(self.budget_id)
                    )
                except ApiException as e:
                    # Log API error and fall back to full sync
                    logger.warning(f"API error during accounts delta sync: {e}")
                    response = self._handle_api_call_with_retry(
                        lambda: accounts_api.get_accounts(self.budget_id)
                    )
                except Exception as e:
                    # Log unexpected error and re-raise
                    logger.error(f"Unexpected error during accounts delta sync: {e}")
                    raise
            else:
                response = self._handle_api_call_with_retry(
                    lambda: accounts_api.get_accounts(self.budget_id)
                )

            return list(response.data.accounts), response.data.server_knowledge

    def _sync_payees_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.Payee], int]:
        """Fetch payees from YNAB API with optional server knowledge."""
        with ynab.ApiClient(self.configuration) as api_client:
            payees_api = ynab.PayeesApi(api_client)

            if last_knowledge is not None:
                try:
                    # Try delta sync first
                    response = self._handle_api_call_with_retry(
                        lambda: payees_api.get_payees(
                            self.budget_id, last_knowledge_of_server=last_knowledge
                        )
                    )
                except ConflictException as e:
                    # Fall back to full sync on stale knowledge
                    logger.info(
                        f"Falling back to full payees sync due to conflict: {e}"
                    )
                    response = self._handle_api_call_with_retry(
                        lambda: payees_api.get_payees(self.budget_id)
                    )
                except ApiException as e:
                    # Log API error and fall back to full sync
                    logger.warning(f"API error during payees delta sync: {e}")
                    response = self._handle_api_call_with_retry(
                        lambda: payees_api.get_payees(self.budget_id)
                    )
                except Exception as e:
                    # Log unexpected error and re-raise
                    logger.error(f"Unexpected error during payees delta sync: {e}")
                    raise
            else:
                response = self._handle_api_call_with_retry(
                    lambda: payees_api.get_payees(self.budget_id)
                )

            return list(response.data.payees), response.data.server_knowledge

    def _sync_category_groups_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.CategoryGroupWithCategories], int]:
        """Fetch category groups from YNAB API with optional server knowledge."""
        with ynab.ApiClient(self.configuration) as api_client:
            categories_api = ynab.CategoriesApi(api_client)

            if last_knowledge is not None:
                try:
                    # Try delta sync first
                    response = self._handle_api_call_with_retry(
                        lambda: categories_api.get_categories(
                            self.budget_id, last_knowledge_of_server=last_knowledge
                        )
                    )
                except ConflictException as e:
                    # Fall back to full sync on stale knowledge
                    logger.info(
                        f"Category groups conflict, falling back to full sync: {e}"
                    )
                    response = self._handle_api_call_with_retry(
                        lambda: categories_api.get_categories(self.budget_id)
                    )
                except ApiException as e:
                    # Log API error and fall back to full sync
                    logger.warning(f"API error during category groups delta sync: {e}")
                    response = self._handle_api_call_with_retry(
                        lambda: categories_api.get_categories(self.budget_id)
                    )
                except Exception as e:
                    # Log unexpected error and re-raise
                    logger.error(
                        f"Unexpected error during category groups delta sync: {e}"
                    )
                    raise
            else:
                response = self._handle_api_call_with_retry(
                    lambda: categories_api.get_categories(self.budget_id)
                )

            return list(response.data.category_groups), response.data.server_knowledge

    def _sync_transactions_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.TransactionDetail], int]:
        """Fetch transactions from YNAB API with optional server knowledge."""
        with ynab.ApiClient(self.configuration) as api_client:
            transactions_api = ynab.TransactionsApi(api_client)

            if last_knowledge is not None:
                try:
                    # Try delta sync first
                    response = self._handle_api_call_with_retry(
                        lambda: transactions_api.get_transactions(
                            self.budget_id, last_knowledge_of_server=last_knowledge
                        )
                    )
                except ConflictException as e:
                    # Fall back to full sync on stale knowledge
                    logger.info(
                        f"Falling back to full transactions sync due to conflict: {e}"
                    )
                    response = self._handle_api_call_with_retry(
                        lambda: transactions_api.get_transactions(self.budget_id)
                    )
                except ApiException as e:
                    # Log API error and fall back to full sync
                    logger.warning(f"API error during transactions delta sync: {e}")
                    response = self._handle_api_call_with_retry(
                        lambda: transactions_api.get_transactions(self.budget_id)
                    )
                except Exception as e:
                    # Log unexpected error and re-raise
                    logger.error(
                        f"Unexpected error during transactions delta sync: {e}"
                    )
                    raise
            else:
                response = self._handle_api_call_with_retry(
                    lambda: transactions_api.get_transactions(self.budget_id)
                )

            return list(response.data.transactions), response.data.server_knowledge

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
        }.get(entity_type)

        if sync_method:
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

    def _handle_api_call_with_retry(
        self, api_call: Callable[[], Any], max_retries: int = 3
    ) -> Any:
        """Handle API call with exponential backoff for rate limiting."""
        for attempt in range(max_retries):
            try:
                return api_call()
            except ConflictException:
                # Let the calling method handle ConflictException for fallback logic
                raise
            except ApiException as e:
                if e.status == 429:
                    # Rate limited - YNAB allows 200 requests/hour
                    wait_time = 2**attempt
                    logger.warning(
                        f"Rate limited - waiting {wait_time}s (retry {attempt + 1})"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("Max retries exceeded for rate limiting")
                        raise
                else:
                    # Other API error - don't retry, let caller handle
                    logger.error(f"API error {e.status}: {e}")
                    raise
            except Exception as e:
                logger.error(f"Unexpected error during API call: {e}")
                raise

    def update_month_category(
        self, category_id: str, month: date, budgeted_milliunits: int
    ) -> ynab.Category:
        """Update a category's budget for a specific month."""
        with ynab.ApiClient(self.configuration) as api_client:
            categories_api = ynab.CategoriesApi(api_client)

            save_month_category = ynab.SaveMonthCategory(budgeted=budgeted_milliunits)
            patch_wrapper = ynab.PatchMonthCategoryWrapper(category=save_month_category)

            response = categories_api.update_month_category(
                self.budget_id, month, category_id, patch_wrapper
            )

            # Invalidate category groups cache since budget amounts changed
            with self._lock:
                if "category_groups" in self._data:
                    del self._data["category_groups"]
                if "category_groups" in self._server_knowledge:
                    del self._server_knowledge["category_groups"]

            return response.data.category

    def update_transaction(
        self, transaction_id: str, update_data: dict[str, Any]
    ) -> ynab.TransactionDetail:
        """Update a transaction with the provided data."""
        with ynab.ApiClient(self.configuration) as api_client:
            transactions_api = ynab.TransactionsApi(api_client)

            # Create the save transaction object
            existing_transaction = ynab.ExistingTransaction(**update_data)
            put_wrapper = ynab.PutTransactionWrapper(transaction=existing_transaction)

            response = transactions_api.update_transaction(
                self.budget_id, transaction_id, put_wrapper
            )

            # Invalidate transactions cache since transaction was modified
            with self._lock:
                if "transactions" in self._data:
                    del self._data["transactions"]
                if "transactions" in self._server_knowledge:
                    del self._server_knowledge["transactions"]

            return response.data.transaction

    def get_transaction_by_id(self, transaction_id: str) -> ynab.TransactionDetail:
        """Get a specific transaction by ID."""
        with ynab.ApiClient(self.configuration) as api_client:
            transactions_api = ynab.TransactionsApi(api_client)
            response = transactions_api.get_transaction_by_id(
                self.budget_id, transaction_id
            )
            return response.data.transaction

    def get_transactions_by_filters(
        self,
        account_id: str | None = None,
        category_id: str | None = None,
        payee_id: str | None = None,
        since_date: date | None = None,
    ) -> list[ynab.TransactionDetail | ynab.HybridTransaction]:
        """Get transactions using specific YNAB API endpoints for filtering."""
        with ynab.ApiClient(self.configuration) as api_client:
            transactions_api = ynab.TransactionsApi(api_client)

            if account_id:
                account_response = transactions_api.get_transactions_by_account(
                    self.budget_id, account_id, since_date=since_date, type=None
                )
                return list(account_response.data.transactions)
            elif category_id:
                category_response = transactions_api.get_transactions_by_category(
                    self.budget_id, category_id, since_date=since_date, type=None
                )
                return list(category_response.data.transactions)
            elif payee_id:
                payee_response = transactions_api.get_transactions_by_payee(
                    self.budget_id, payee_id, since_date=since_date, type=None
                )
                return list(payee_response.data.transactions)
            else:
                # Use general transactions endpoint
                general_response = transactions_api.get_transactions(
                    self.budget_id, since_date=since_date, type=None
                )
                return list(general_response.data.transactions)

    def get_scheduled_transactions(self) -> list[ynab.ScheduledTransactionDetail]:
        """Get scheduled transactions."""
        with ynab.ApiClient(self.configuration) as api_client:
            scheduled_transactions_api = ynab.ScheduledTransactionsApi(api_client)
            response = scheduled_transactions_api.get_scheduled_transactions(
                self.budget_id
            )
            return list(response.data.scheduled_transactions)

    def get_month_category_by_id(self, month: date, category_id: str) -> ynab.Category:
        """Get a specific category for a specific month."""
        with ynab.ApiClient(self.configuration) as api_client:
            categories_api = ynab.CategoriesApi(api_client)
            response = categories_api.get_month_category_by_id(
                self.budget_id, month, category_id
            )
            return response.data.category

    def get_budget_month(self, month: date) -> ynab.MonthDetail:
        """Get budget month data for a specific month."""
        with ynab.ApiClient(self.configuration) as api_client:
            months_api = ynab.MonthsApi(api_client)
            response = months_api.get_budget_month(self.budget_id, month)
            return response.data.month
