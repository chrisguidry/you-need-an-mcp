"""
Test how the repository syncs category groups from YNAB, in full and by delta.
"""

from unittest.mock import MagicMock, create_autospec, patch

import ynab
from conftest import (
    create_ynab_category_group,
)
from ids import uid

from repository import YNABRepository


def seed_category_groups(
    repository: YNABRepository,
    category_groups: list[ynab.CategoryGroupWithCategories],
    server_knowledge: int = 100,
) -> None:
    """Load category groups into a repository the way a sync from YNAB does."""
    api = create_autospec(ynab.CategoriesApi, instance=True)
    api.get_categories.return_value = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=category_groups, server_knowledge=server_knowledge
        )
    )
    with patch("ynab.CategoriesApi", return_value=api):
        repository.sync_category_groups()


def test_repository_category_groups_initial_sync(repository: YNABRepository) -> None:
    """Test repository initial sync for category groups without server knowledge."""
    group1 = create_ynab_category_group(id=uid("group-1"), name="Monthly Bills")
    group2 = create_ynab_category_group(id=uid("group-2"), name="Everyday Expenses")

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[group1, group2], server_knowledge=100
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = categories_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            repository.sync_category_groups()

    # Verify initial sync called without last_knowledge_of_server
    mock_categories_api.get_categories.assert_called_once_with("test-budget")

    # Verify data was stored
    category_groups = repository.get_category_groups()
    assert len(category_groups) == 2
    assert category_groups[0].id == uid("group-1")
    assert category_groups[1].id == uid("group-2")

    # Verify server knowledge was stored
    assert repository.server_knowledge("category_groups") == 100


def test_repository_category_groups_delta_sync(repository: YNABRepository) -> None:
    """Test repository delta sync for category groups with server knowledge."""
    # Set up initial state
    group1 = create_ynab_category_group(id=uid("group-1"), name="Monthly Bills")
    seed_category_groups(repository, [group1])

    # Delta sync with updated group and new group
    updated_group1 = create_ynab_category_group(
        id=uid("group-1"), name="Fixed Expenses"
    )
    new_group = create_ynab_category_group(id=uid("group-2"), name="Variable Expenses")

    delta_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[updated_group1, new_group], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = delta_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            repository.sync_category_groups()

    # Verify delta sync called with last_knowledge_of_server
    mock_categories_api.get_categories.assert_called_once_with(
        "test-budget", last_knowledge_of_server=100
    )

    # Verify deltas were applied
    category_groups = repository.get_category_groups()
    assert len(category_groups) == 2

    # Find groups by ID
    g1 = next(g for g in category_groups if g.id == uid("group-1"))
    g2 = next(g for g in category_groups if g.id == uid("group-2"))

    assert g1.name == "Fixed Expenses"  # Updated
    assert g2.name == "Variable Expenses"  # Added

    # Verify server knowledge was updated
    assert repository.server_knowledge("category_groups") == 110


def test_repository_category_groups_handles_deleted(repository: YNABRepository) -> None:
    """Test repository handles deleted category groups in delta sync."""
    # Set up initial state with two groups
    group1 = create_ynab_category_group(id=uid("group-1"), name="Monthly Bills")
    group2 = create_ynab_category_group(id=uid("group-2"), name="Old Category")
    seed_category_groups(repository, [group1, group2])

    # Delta with one deleted group
    deleted_group = create_ynab_category_group(
        id=uid("group-2"), name="Old Category", deleted=True
    )

    delta_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(
            category_groups=[deleted_group], server_knowledge=110
        )
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = delta_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            repository.sync_category_groups()

    # Verify deleted group was removed
    category_groups = repository.get_category_groups()
    assert len(category_groups) == 1
    assert category_groups[0].id == uid("group-1")  # Only Monthly Bills remains


def test_repository_category_groups_lazy_initialization(
    repository: YNABRepository,
) -> None:
    """Test category groups repository initializes automatically when data requested."""
    group1 = create_ynab_category_group(id=uid("group-1"), name="Monthly Bills")

    categories_response = ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(category_groups=[group1], server_knowledge=100)
    )

    with patch("ynab.ApiClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_categories_api = MagicMock()
        mock_categories_api.get_categories.return_value = categories_response

        with patch("ynab.CategoriesApi", return_value=mock_categories_api):
            # Repository category groups is not initialized initially
            assert not repository.is_initialized()

            # Calling get_category_groups should trigger sync
            category_groups = repository.get_category_groups()

    # Verify sync was called
    mock_categories_api.get_categories.assert_called_once()

    # Verify data is available
    assert len(category_groups) == 1
    assert category_groups[0].id == uid("group-1")
