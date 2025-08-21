"""
Test fixtures for YNAB MCP Server tests.

This module contains pytest fixtures for testing without calling the actual YNAB API.
"""

import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import fastmcp
import pytest
import ynab
from fastmcp.client import Client, FastMCPTransport

# Add parent directory to path to import server module
sys.path.insert(0, str(Path(__file__).parent.parent))
import server


@pytest.fixture
def mock_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock environment variables for testing."""
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token_123")
    monkeypatch.setenv("YNAB_BUDGET", "test_budget_id")


@pytest.fixture
def ynab_client(mock_environment_variables: None) -> Generator[MagicMock, None, None]:
    """Mock YNAB client with proper autospec for testing."""
    mock_client = MagicMock(spec=ynab.ApiClient)
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    yield mock_client


@pytest.fixture
def mock_repository() -> Generator[MagicMock, None, None]:
    """Mock the repository to prevent API calls during testing."""
    with patch("server._repository") as mock_repo:
        yield mock_repo


@pytest.fixture
def categories_api(ynab_client: MagicMock) -> Generator[MagicMock, None, None]:
    mock_api = Mock(spec=ynab.CategoriesApi)
    with patch("ynab.CategoriesApi", return_value=mock_api):
        yield mock_api


@pytest.fixture
def months_api(ynab_client: MagicMock) -> Generator[MagicMock, None, None]:
    mock_api = Mock(spec=ynab.MonthsApi)
    with patch("ynab.MonthsApi", return_value=mock_api):
        yield mock_api


@pytest.fixture
def transactions_api(ynab_client: MagicMock) -> Generator[MagicMock, None, None]:
    mock_api = Mock(spec=ynab.TransactionsApi)
    with patch("ynab.TransactionsApi", return_value=mock_api):
        yield mock_api


@pytest.fixture
def scheduled_transactions_api(
    ynab_client: MagicMock,
) -> Generator[MagicMock, None, None]:
    mock_api = Mock(spec=ynab.ScheduledTransactionsApi)
    with patch("ynab.ScheduledTransactionsApi", return_value=mock_api):
        yield mock_api


@pytest.fixture
async def mcp_client() -> AsyncGenerator[Client[FastMCPTransport], None]:
    """Mock MCP client with proper autospec for testing."""
    async with fastmcp.Client(server.mcp) as client:
        yield client
