"""
YNAB Repository with differential sync.

Provides local-first access to YNAB data with background synchronization.
"""

import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

import ynab


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

    def get_accounts(self) -> list[ynab.Account]:
        """Get all accounts from local repository."""
        if not self.is_initialized():
            self.sync_accounts()

        with self._lock:
            return self._data.get("accounts", [])

    def get_payees(self) -> list[ynab.Payee]:
        """Get all payees from local repository."""
        if "payees" not in self._data:
            self.sync_payees()

        with self._lock:
            return self._data.get("payees", [])

    def sync_accounts(self) -> None:
        """Sync accounts with YNAB API using differential sync."""
        self._sync_entity("accounts", self._sync_accounts_from_api)

    def sync_payees(self) -> None:
        """Sync payees with YNAB API using differential sync."""
        self._sync_entity("payees", self._sync_payees_from_api)

    def _sync_accounts_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.Account], int]:
        """Fetch accounts from YNAB API with optional server knowledge."""
        with ynab.ApiClient(self.configuration) as api_client:
            accounts_api = ynab.AccountsApi(api_client)

            if last_knowledge is not None:
                try:
                    response = accounts_api.get_accounts(
                        self.budget_id, last_knowledge_of_server=last_knowledge
                    )
                except Exception:
                    # If delta sync fails, fall back to full sync
                    response = accounts_api.get_accounts(self.budget_id)
                    # Signal full refresh by returning None for last_knowledge
                    return list(response.data.accounts), response.data.server_knowledge
            else:
                response = accounts_api.get_accounts(self.budget_id)

            return list(response.data.accounts), response.data.server_knowledge

    def _sync_payees_from_api(
        self, last_knowledge: int | None
    ) -> tuple[list[ynab.Payee], int]:
        """Fetch payees from YNAB API with optional server knowledge."""
        with ynab.ApiClient(self.configuration) as api_client:
            payees_api = ynab.PayeesApi(api_client)

            if last_knowledge is not None:
                try:
                    response = payees_api.get_payees(
                        self.budget_id, last_knowledge_of_server=last_knowledge
                    )
                except Exception:
                    # If delta sync fails, fall back to full sync
                    response = payees_api.get_payees(self.budget_id)
                    # Signal full refresh by returning None for last_knowledge
                    return list(response.data.payees), response.data.server_knowledge
            else:
                response = payees_api.get_payees(self.budget_id)

            return list(response.data.payees), response.data.server_knowledge

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
