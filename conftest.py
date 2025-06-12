"""
Test fixtures for YNAB MCP Server tests.

This module contains pytest fixtures for testing without calling the actual YNAB API.
"""

import pytest


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token_123")
    monkeypatch.setenv("YNAB_DEFAULT_BUDGET", "budget-123")