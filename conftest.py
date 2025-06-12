"""
Test fixtures for YNAB MCP Server tests.

This module contains pytest fixtures with realistic YNAB API response data
to enable comprehensive testing without calling the actual YNAB API.
"""

import pytest
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import Mock, MagicMock
import ynab

from server import mcp


@pytest.fixture
def mock_ynab_client():
    """Mock YNAB API client with realistic response data."""
    mock_client = MagicMock()
    
    # Mock currency format
    mock_currency_format = Mock()
    mock_currency_format.iso_code = "USD"
    mock_currency_format.example_format = "$123.45"
    mock_currency_format.decimal_digits = 2
    mock_currency_format.decimal_separator = "."
    mock_currency_format.symbol_first = True
    mock_currency_format.group_separator = ","
    mock_currency_format.currency_symbol = "$"
    mock_currency_format.display_symbol = True
    
    # Mock budget data
    mock_budget = Mock()
    mock_budget.id = "budget-123"
    mock_budget.name = "Test Budget"
    mock_budget.last_modified_on = datetime(2024, 1, 15, 10, 30, 0)
    mock_budget.first_month = datetime(2024, 1, 1)
    mock_budget.last_month = datetime(2024, 12, 1)
    mock_budget.currency_format = mock_currency_format
    
    # Mock account data
    mock_account = Mock()
    mock_account.id = "account-456"
    mock_account.name = "Test Checking"
    mock_account.type = "checking"
    mock_account.on_budget = True
    mock_account.closed = False
    mock_account.note = "Primary checking account"
    mock_account.balance = 125000  # $125.00 in milliunits
    mock_account.cleared_balance = 120000  # $120.00
    mock_account.uncleared_balance = 5000   # $5.00
    mock_account.transfer_payee_id = "payee-789"
    mock_account.direct_import_linked = True
    mock_account.direct_import_in_error = False
    mock_account.last_reconciled_at = datetime(2024, 1, 10, 9, 0, 0)
    mock_account.debt_original_balance = None
    
    mock_closed_account = Mock()
    mock_closed_account.id = "account-closed"
    mock_closed_account.name = "Closed Account"
    mock_closed_account.type = "savings"
    mock_closed_account.on_budget = False
    mock_closed_account.closed = True
    mock_closed_account.note = None
    mock_closed_account.balance = 0
    mock_closed_account.cleared_balance = 0
    mock_closed_account.uncleared_balance = 0
    mock_closed_account.transfer_payee_id = None
    mock_closed_account.direct_import_linked = False
    mock_closed_account.direct_import_in_error = False
    mock_closed_account.last_reconciled_at = None
    mock_closed_account.debt_original_balance = None
    
    # Mock category group and categories
    mock_category_group = Mock()
    mock_category_group.id = "group-111"
    mock_category_group.name = "Monthly Bills"
    mock_category_group.hidden = False
    mock_category_group.deleted = False
    
    mock_category = Mock()
    mock_category.id = "category-222"
    mock_category.name = "Groceries"
    mock_category.category_group_id = "group-111"
    mock_category.hidden = False
    mock_category.deleted = False
    mock_category.note = "Food and household items"
    mock_category.budgeted = 50000  # $50.00
    mock_category.activity = -35000  # -$35.00 (spent)
    mock_category.balance = 15000   # $15.00 remaining
    mock_category.goal_type = "TB"
    mock_category.goal_target = 100000  # $100.00
    mock_category.goal_percentage_complete = 50
    mock_category.goal_under_funded = 0
    
    mock_hidden_category = Mock()
    mock_hidden_category.id = "category-hidden"
    mock_hidden_category.name = "Hidden Category"
    mock_hidden_category.category_group_id = "group-111"
    mock_hidden_category.hidden = True
    mock_hidden_category.deleted = False
    mock_hidden_category.note = None
    mock_hidden_category.budgeted = 10000
    mock_hidden_category.activity = 0
    mock_hidden_category.balance = 10000
    mock_hidden_category.goal_type = None
    mock_hidden_category.goal_target = None
    mock_hidden_category.goal_percentage_complete = None
    mock_hidden_category.goal_under_funded = None
    
    mock_category_group.categories = [mock_category, mock_hidden_category]
    
    # Mock month data
    mock_month = Mock()
    mock_month.month = datetime(2024, 1, 1)
    mock_month.note = "January budget"
    mock_month.income = 400000  # $400.00
    mock_month.budgeted = 350000  # $350.00
    mock_month.activity = -200000  # -$200.00
    mock_month.to_be_budgeted = 50000  # $50.00
    mock_month.age_of_money = 15
    mock_month.categories = [mock_category, mock_hidden_category]
    
    # Configure API responses
    mock_budgets_response = Mock()
    mock_budgets_response.data.budgets = [mock_budget]
    
    mock_accounts_response = Mock()
    mock_accounts_response.data.accounts = [mock_account, mock_closed_account]
    
    mock_categories_response = Mock()
    mock_categories_response.data.category_groups = [mock_category_group]
    
    mock_month_response = Mock()
    mock_month_response.data.month = mock_month
    
    mock_category_response = Mock()
    mock_category_response.data.category = mock_category
    
    # Configure API mocks
    mock_budgets_api = Mock()
    mock_budgets_api.get_budgets.return_value = mock_budgets_response
    
    mock_accounts_api = Mock()
    mock_accounts_api.get_accounts.return_value = mock_accounts_response
    
    mock_categories_api = Mock()
    mock_categories_api.get_categories.return_value = mock_categories_response
    
    mock_months_api = Mock()
    mock_months_api.get_budget_month.return_value = mock_month_response
    mock_months_api.get_month_category_by_id.return_value = mock_category_response
    
    # Configure client to return API instances
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    
    # Patch the API classes to return our mocks
    with pytest.MonkeyPatch().context() as m:
        m.setattr(ynab, "BudgetsApi", lambda client: mock_budgets_api)
        m.setattr(ynab, "AccountsApi", lambda client: mock_accounts_api)
        m.setattr(ynab, "CategoriesApi", lambda client: mock_categories_api)
        m.setattr(ynab, "MonthsApi", lambda client: mock_months_api)
        
        yield mock_client


@pytest.fixture
def mcp_server():
    """FastMCP server instance for testing."""
    return mcp


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token_123")
    monkeypatch.setenv("YNAB_DEFAULT_BUDGET", "budget-123")