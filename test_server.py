"""
Comprehensive test suite for YNAB MCP Server.

Tests all MCP tools with mocked YNAB API responses to ensure 100% coverage
and correct functionality without requiring actual YNAB API access.
"""

import pytest
import json
from decimal import Decimal
from datetime import datetime, date
from unittest.mock import patch, Mock, MagicMock
from fastmcp import Client

from models import Budget, Account, Category, CategoryGroup, BudgetMonth, CurrencyFormat, PaginationInfo
import server


class TestUtilityFunctions:
    """Test utility functions in server module."""
    
    def test_milliunits_to_currency_valid_input(self):
        """Test milliunits conversion with valid input."""
        result = server.milliunits_to_currency(123456)
        assert result == Decimal('123.456')
    
    def test_milliunits_to_currency_none_input(self):
        """Test milliunits conversion with None input."""
        result = server.milliunits_to_currency(None)
        assert result is None
    
    def test_milliunits_to_currency_zero(self):
        """Test milliunits conversion with zero."""
        result = server.milliunits_to_currency(0)
        assert result == Decimal('0')
    
    def test_milliunits_to_currency_negative(self):
        """Test milliunits conversion with negative value."""
        result = server.milliunits_to_currency(-50000)
        assert result == Decimal('-50')

    def test_get_default_budget_id_with_env_var(self, monkeypatch):
        """Test getting default budget ID when environment variable is set."""
        monkeypatch.setenv("YNAB_DEFAULT_BUDGET", "test-budget-123")
        result = server.get_default_budget_id()
        assert result == "test-budget-123"
    
    def test_get_default_budget_id_missing_env_var(self, monkeypatch):
        """Test getting default budget ID when environment variable is missing."""
        monkeypatch.delenv("YNAB_DEFAULT_BUDGET", raising=False)
        with pytest.raises(ValueError, match="budget_id is required"):
            server.get_default_budget_id()

    def test_get_ynab_client_with_token(self, monkeypatch):
        """Test YNAB client creation with valid token."""
        monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token")
        with patch('ynab.Configuration') as mock_config, \
             patch('ynab.ApiClient') as mock_client:
            
            result = server.get_ynab_client()
            mock_config.assert_called_once_with(access_token="test_token")
            mock_client.assert_called_once()

    def test_get_ynab_client_missing_token(self, monkeypatch):
        """Test YNAB client creation without token."""
        monkeypatch.delenv("YNAB_ACCESS_TOKEN", raising=False)
        with pytest.raises(ValueError, match="YNAB_ACCESS_TOKEN environment variable is required"):
            server.get_ynab_client()

    def test_convert_month_to_date_with_date_object(self):
        """Test convert_month_to_date with date object returns unchanged."""
        test_date = date(2024, 3, 15)
        result = server.convert_month_to_date(test_date)
        assert result == test_date
    
    def test_convert_month_to_date_with_current(self):
        """Test convert_month_to_date with 'current' returns current month date."""
        from unittest.mock import patch
        from datetime import datetime
        
        with patch('server.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 9, 20, 16, 45, 0)
            
            result = server.convert_month_to_date("current")
            assert result == date(2024, 9, 1)
    
    def test_convert_month_to_date_with_last_and_next(self):
        """Test convert_month_to_date with 'last' and 'next' literals."""
        from unittest.mock import patch
        from datetime import datetime
        
        # Test normal month (June -> May and July)
        with patch('server.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 6, 15, 10, 30, 0)
            
            result_last = server.convert_month_to_date("last")
            assert result_last == date(2024, 5, 1)
            
            result_next = server.convert_month_to_date("next")
            assert result_next == date(2024, 7, 1)
        
        # Test January edge case (January -> December previous year)
        with patch('server.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 1, 10, 14, 45, 0)
            
            result_last = server.convert_month_to_date("last")
            assert result_last == date(2023, 12, 1)
            
            result_next = server.convert_month_to_date("next")
            assert result_next == date(2024, 2, 1)
        
        # Test December edge case (December -> January next year)
        with patch('server.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2024, 12, 25, 9, 15, 0)
            
            result_last = server.convert_month_to_date("last")
            assert result_last == date(2024, 11, 1)
            
            result_next = server.convert_month_to_date("next")
            assert result_next == date(2025, 1, 1)
    
    def test_convert_month_to_date_invalid_value(self):
        """Test convert_month_to_date with invalid value raises error."""
        with pytest.raises(ValueError, match="Invalid month value: invalid"):
            server.convert_month_to_date("invalid")


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token_123")
    monkeypatch.setenv("YNAB_DEFAULT_BUDGET", "budget-123")


class TestMCPTools:
    """Test all MCP tools using FastMCP testing patterns."""
    
    @pytest.mark.asyncio
    async def test_list_budgets_success(self, mock_env_vars):
        """Test successful budget listing."""
        with patch('server.get_ynab_client') as mock_get_client:
            # Create mock context manager
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Setup mock budget data
            mock_budget = Mock()
            mock_budget.id = "budget-123"
            mock_budget.name = "Test Budget"
            mock_budget.last_modified_on = datetime(2024, 1, 15, 10, 30, 0)
            mock_budget.first_month = date(2024, 1, 1)  # YNAB returns date, not datetime
            mock_budget.last_month = date(2024, 12, 1)   # YNAB returns date, not datetime
            
            mock_currency_format = Mock()
            mock_currency_format.iso_code = "USD"
            mock_currency_format.example_format = "$123.45"
            mock_currency_format.decimal_digits = 2
            mock_currency_format.decimal_separator = "."
            mock_currency_format.symbol_first = True
            mock_currency_format.group_separator = ","
            mock_currency_format.currency_symbol = "$"
            mock_currency_format.display_symbol = True
            mock_budget.currency_format = mock_currency_format
            
            mock_response = Mock()
            mock_response.data.budgets = [mock_budget]
            
            mock_budgets_api = Mock()
            mock_budgets_api.get_budgets.return_value = mock_response
            
            with patch('ynab.BudgetsApi', return_value=mock_budgets_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_budgets", {})
                    
                    assert len(result) == 1
                    # The result is a list of Budget objects serialized as JSON
                    budgets_data = json.loads(result[0].text)
                    # budgets_data is a single Budget object, not a list
                    assert budgets_data['id'] == "budget-123"
                    assert budgets_data['name'] == "Test Budget"

    @pytest.mark.asyncio
    async def test_list_budgets_null_currency(self, mock_env_vars):
        """Test budget listing with null currency format."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            mock_budget = Mock()
            mock_budget.id = "budget-456"
            mock_budget.name = "Budget No Currency"
            mock_budget.last_modified_on = None
            mock_budget.first_month = None
            mock_budget.last_month = None
            mock_budget.currency_format = None
            
            mock_response = Mock()
            mock_response.data.budgets = [mock_budget]
            
            mock_budgets_api = Mock()
            mock_budgets_api.get_budgets.return_value = mock_response
            
            with patch('ynab.BudgetsApi', return_value=mock_budgets_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_budgets", {})
                    
                    assert len(result) == 1
                    budgets_data = json.loads(result[0].text)
                    assert budgets_data['id'] == "budget-456"
                    assert budgets_data['currency_format'] is None

    @pytest.mark.asyncio
    async def test_list_accounts_success(self, mock_env_vars):
        """Test successful account listing."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock accounts
            mock_account1 = Mock()
            mock_account1.id = "acc-1"
            mock_account1.name = "Checking"
            mock_account1.type = "checking"
            mock_account1.on_budget = True
            mock_account1.closed = False
            mock_account1.note = "Main account"
            mock_account1.balance = 100000  # $100.00
            mock_account1.cleared_balance = 95000
            mock_account1.uncleared_balance = 5000
            mock_account1.transfer_payee_id = "payee-1"
            mock_account1.direct_import_linked = True
            mock_account1.direct_import_in_error = False
            mock_account1.last_reconciled_at = datetime(2024, 1, 10, 9, 0, 0)
            mock_account1.debt_original_balance = None
            
            mock_account2 = Mock()
            mock_account2.id = "acc-2"
            mock_account2.name = "Savings"
            mock_account2.type = "savings"
            mock_account2.on_budget = False
            mock_account2.closed = True  # Closed account - should be excluded
            mock_account2.note = None
            mock_account2.balance = 0
            mock_account2.cleared_balance = 0
            mock_account2.uncleared_balance = 0
            mock_account2.transfer_payee_id = None
            mock_account2.direct_import_linked = False
            mock_account2.direct_import_in_error = False
            mock_account2.last_reconciled_at = None
            mock_account2.debt_original_balance = None
            
            mock_response = Mock()
            mock_response.data.accounts = [mock_account1, mock_account2]
            
            mock_accounts_api = Mock()
            mock_accounts_api.get_accounts.return_value = mock_response
            
            with patch('ynab.AccountsApi', return_value=mock_accounts_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_accounts", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should only include open account
                    assert len(response_data['accounts']) == 1
                    assert response_data['accounts'][0]['id'] == "acc-1"
                    assert response_data['accounts'][0]['name'] == "Checking"

    @pytest.mark.asyncio
    async def test_list_accounts_include_closed(self, mock_env_vars):
        """Test account listing including closed accounts."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            mock_account = Mock()
            mock_account.id = "acc-closed"
            mock_account.name = "Closed Account"
            mock_account.type = "savings"
            mock_account.on_budget = False
            mock_account.closed = True
            mock_account.note = None
            mock_account.balance = 0
            mock_account.cleared_balance = 0
            mock_account.uncleared_balance = 0
            mock_account.transfer_payee_id = None
            mock_account.direct_import_linked = False
            mock_account.direct_import_in_error = False
            mock_account.last_reconciled_at = None
            mock_account.debt_original_balance = None
            
            mock_response = Mock()
            mock_response.data.accounts = [mock_account]
            
            mock_accounts_api = Mock()
            mock_accounts_api.get_accounts.return_value = mock_response
            
            with patch('ynab.AccountsApi', return_value=mock_accounts_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_accounts", {"include_closed": True})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert len(response_data['accounts']) == 1
                    assert response_data['accounts'][0]['id'] == "acc-closed"

    @pytest.mark.asyncio
    async def test_list_categories_success(self, mock_env_vars):
        """Test successful category listing."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock category group and categories
            mock_category_group = Mock()
            mock_category_group.name = "Monthly Bills"
            
            mock_category = Mock()
            mock_category.id = "cat-1"
            mock_category.name = "Groceries"
            mock_category.category_group_id = "group-1"
            mock_category.hidden = False
            mock_category.deleted = False
            mock_category.note = "Food shopping"
            mock_category.budgeted = 50000
            mock_category.activity = -30000
            mock_category.balance = 20000
            mock_category.goal_type = "TB"
            mock_category.goal_target = 100000
            mock_category.goal_percentage_complete = 50
            mock_category.goal_under_funded = 0
            
            mock_hidden_category = Mock()
            mock_hidden_category.id = "cat-hidden"
            mock_hidden_category.name = "Hidden Category"
            mock_hidden_category.category_group_id = "group-1"
            mock_hidden_category.hidden = True  # Should be excluded by default
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
            
            mock_response = Mock()
            mock_response.data.category_groups = [mock_category_group]
            
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = mock_response
            
            with patch('ynab.CategoriesApi', return_value=mock_categories_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_categories", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should only include visible category
                    assert len(response_data['categories']) == 1
                    assert response_data['categories'][0]['id'] == "cat-1"
                    assert response_data['categories'][0]['name'] == "Groceries"

    @pytest.mark.asyncio
    async def test_list_category_groups_success(self, mock_env_vars):
        """Test successful category group listing."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock category and group
            mock_category = Mock()
            mock_category.budgeted = 50000
            mock_category.activity = -30000
            mock_category.balance = 20000
            mock_category.deleted = False
            mock_category.hidden = False
            
            mock_category_group = Mock()
            mock_category_group.id = "group-1"
            mock_category_group.name = "Monthly Bills"
            mock_category_group.hidden = False
            mock_category_group.deleted = False
            mock_category_group.categories = [mock_category]
            
            mock_response = Mock()
            mock_response.data.category_groups = [mock_category_group]
            
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = mock_response
            
            with patch('ynab.CategoriesApi', return_value=mock_categories_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_category_groups", {})
                    
                    assert len(result) == 1
                    groups_data = json.loads(result[0].text)
                    # groups_data is a single group object
                    assert groups_data['id'] == "group-1"
                    assert groups_data['name'] == "Monthly Bills"

    @pytest.mark.asyncio
    async def test_get_budget_month_success(self, mock_env_vars):
        """Test successful budget month retrieval."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock category
            mock_category = Mock()
            mock_category.id = "cat-1"
            mock_category.name = "Groceries"
            mock_category.category_group_id = "group-1"
            mock_category.hidden = False
            mock_category.deleted = False
            mock_category.note = "Food"
            mock_category.budgeted = 50000
            mock_category.activity = -30000
            mock_category.balance = 20000
            mock_category.goal_type = "TB"
            mock_category.goal_target = 100000
            mock_category.goal_percentage_complete = 50
            mock_category.goal_under_funded = 0
            
            # Create mock month
            mock_month = Mock()
            mock_month.month = date(2024, 1, 1)  # YNAB returns date, not datetime
            mock_month.note = "January budget"
            mock_month.income = 400000
            mock_month.budgeted = 350000
            mock_month.activity = -200000
            mock_month.to_be_budgeted = 50000
            mock_month.age_of_money = 15
            mock_month.categories = [mock_category]
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert response_data['note'] == "January budget"
                    assert len(response_data['categories']) == 1
                    assert response_data['categories'][0]['id'] == "cat-1"

    @pytest.mark.asyncio
    async def test_get_month_category_by_id_success(self, mock_env_vars):
        """Test successful month category retrieval by ID."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            mock_category = Mock()
            mock_category.id = "cat-123"
            mock_category.name = "Groceries"
            mock_category.category_group_id = "group-1"
            mock_category.hidden = False
            mock_category.note = "Food shopping"
            mock_category.budgeted = 50000
            mock_category.activity = -30000
            mock_category.balance = 20000
            mock_category.goal_type = "TB"
            mock_category.goal_target = 100000
            mock_category.goal_percentage_complete = 50
            mock_category.goal_under_funded = 0
            
            mock_response = Mock()
            mock_response.data.category = mock_category
            
            mock_months_api = Mock()
            mock_months_api.get_month_category_by_id.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_month_category_by_id", {
                        "category_id": "cat-123",
                        "budget_id": "budget-123"
                    })
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert response_data['id'] == "cat-123"
                    assert response_data['name'] == "Groceries"
                    assert response_data['note'] == "Food shopping"

    @pytest.mark.asyncio
    async def test_list_categories_with_deleted_categories(self, mock_env_vars):
        """Test category listing filters out deleted categories."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock category group and categories
            mock_category_group = Mock()
            mock_category_group.name = "Monthly Bills"
            
            mock_deleted_category = Mock()
            mock_deleted_category.id = "cat-deleted"
            mock_deleted_category.name = "Deleted Category"
            mock_deleted_category.category_group_id = "group-1"
            mock_deleted_category.hidden = False
            mock_deleted_category.deleted = True  # Should be excluded
            mock_deleted_category.note = "Deleted"
            mock_deleted_category.budgeted = 0
            mock_deleted_category.activity = 0
            mock_deleted_category.balance = 0
            mock_deleted_category.goal_type = None
            mock_deleted_category.goal_target = None
            mock_deleted_category.goal_percentage_complete = None
            mock_deleted_category.goal_under_funded = None
            
            mock_category_group.categories = [mock_deleted_category]
            
            mock_response = Mock()
            mock_response.data.category_groups = [mock_category_group]
            
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = mock_response
            
            with patch('ynab.CategoriesApi', return_value=mock_categories_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_categories", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should exclude deleted category
                    assert len(response_data['categories']) == 0

    @pytest.mark.asyncio
    async def test_list_category_groups_with_deleted_group(self, mock_env_vars):
        """Test category group listing filters out deleted groups."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            mock_category_group = Mock()
            mock_category_group.id = "group-deleted"
            mock_category_group.name = "Deleted Group"
            mock_category_group.hidden = False
            mock_category_group.deleted = True  # Should be excluded
            mock_category_group.categories = []
            
            mock_response = Mock()
            mock_response.data.category_groups = [mock_category_group]
            
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = mock_response
            
            with patch('ynab.CategoriesApi', return_value=mock_categories_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_category_groups", {})
                    
                    # When all groups are deleted, result should be empty
                    assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_budget_month_with_deleted_categories(self, mock_env_vars):
        """Test budget month filters out deleted categories."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock deleted category
            mock_deleted_category = Mock()
            mock_deleted_category.id = "cat-deleted"
            mock_deleted_category.name = "Deleted"
            mock_deleted_category.category_group_id = "group-1"
            mock_deleted_category.hidden = False
            mock_deleted_category.deleted = True  # Should be excluded
            mock_deleted_category.note = "Deleted"
            mock_deleted_category.budgeted = 0
            mock_deleted_category.activity = 0
            mock_deleted_category.balance = 0
            mock_deleted_category.goal_type = None
            mock_deleted_category.goal_target = None
            mock_deleted_category.goal_percentage_complete = None
            mock_deleted_category.goal_under_funded = None
            
            # Create mock month
            mock_month = Mock()
            mock_month.month = date(2024, 1, 1)  # YNAB returns date, not datetime
            mock_month.note = "January budget"
            mock_month.income = 400000
            mock_month.budgeted = 350000
            mock_month.activity = -200000
            mock_month.to_be_budgeted = 50000
            mock_month.age_of_money = 15
            mock_month.categories = [mock_deleted_category]
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should exclude deleted category
                    assert len(response_data['categories']) == 0

    @pytest.mark.asyncio  
    async def test_get_budget_month_with_default_budget(self, mock_env_vars):
        """Test budget month uses default budget ID when none provided."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock month with no categories
            mock_month = Mock()
            mock_month.month = None  # Test None month
            mock_month.note = None
            mock_month.income = None
            mock_month.budgeted = None
            mock_month.activity = None
            mock_month.to_be_budgeted = None
            mock_month.age_of_money = None
            mock_month.categories = []
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert response_data['month'] is None
                    assert response_data['note'] is None
                    assert len(response_data['categories']) == 0

    @pytest.mark.asyncio
    async def test_get_budget_month_with_hidden_categories(self, mock_env_vars):
        """Test budget month filters out hidden categories by default."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock hidden category
            mock_hidden_category = Mock()
            mock_hidden_category.id = "cat-hidden"
            mock_hidden_category.name = "Hidden"
            mock_hidden_category.category_group_id = "group-1"
            mock_hidden_category.hidden = True  # Should be excluded by default
            mock_hidden_category.deleted = False
            mock_hidden_category.note = "Hidden"
            mock_hidden_category.budgeted = 10000
            mock_hidden_category.activity = 0
            mock_hidden_category.balance = 10000
            mock_hidden_category.goal_type = None
            mock_hidden_category.goal_target = None
            mock_hidden_category.goal_percentage_complete = None
            mock_hidden_category.goal_under_funded = None
            
            # Create mock month
            mock_month = Mock()
            mock_month.month = date(2024, 1, 1)  # YNAB returns date, not datetime
            mock_month.note = "January budget"
            mock_month.income = 400000
            mock_month.budgeted = 350000
            mock_month.activity = -200000
            mock_month.to_be_budgeted = 50000
            mock_month.age_of_money = 15
            mock_month.categories = [mock_hidden_category]
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should exclude hidden category
                    assert len(response_data['categories']) == 0


class TestDataTypeHandling:
    """Test proper handling of financial values, dates, and datetimes through the full pipeline."""
    
    def test_decimal_precision_milliunits_conversion(self):
        """Test that milliunits conversion maintains Decimal precision."""
        # Test various milliunits values that could lose precision with floats
        test_cases = [
            (123456, Decimal('123.456')),  # Regular amount
            (1, Decimal('0.001')),         # Smallest unit
            (999, Decimal('0.999')),       # Just under 1
            (1000, Decimal('1')),          # Exactly 1
            (1001, Decimal('1.001')),      # Just over 1
            (999999999, Decimal('999999.999')),  # Large amount
            (-50000, Decimal('-50')),      # Negative amount
            (0, Decimal('0')),             # Zero
        ]
        
        for milliunits, expected in test_cases:
            result = server.milliunits_to_currency(milliunits)
            assert result == expected, f"Failed for {milliunits}: got {result}, expected {expected}"
            # Ensure result is actually a Decimal, not float
            assert isinstance(result, Decimal), f"Result {result} is not a Decimal but {type(result)}"
    
    @pytest.mark.asyncio
    async def test_financial_precision_through_json_serialization(self, mock_env_vars):
        """Test that Decimal precision is maintained through JSON serialization in MCP tools."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock account with precise milliunits that would lose precision as float
            mock_account = Mock()
            mock_account.id = "acc-precision"
            mock_account.name = "Precision Test"
            mock_account.type = "checking"
            mock_account.on_budget = True
            mock_account.closed = False
            mock_account.note = None
            mock_account.balance = 123456789  # $123,456.789 - tests 3 decimal precision
            mock_account.cleared_balance = 999999999  # $999,999.999 - large precise amount
            mock_account.uncleared_balance = 1  # $0.001 - smallest unit
            mock_account.transfer_payee_id = None
            mock_account.direct_import_linked = False
            mock_account.direct_import_in_error = False
            mock_account.last_reconciled_at = None
            mock_account.debt_original_balance = -123001  # -$123.001
            
            mock_response = Mock()
            mock_response.data.accounts = [mock_account]
            
            mock_accounts_api = Mock()
            mock_accounts_api.get_accounts.return_value = mock_response
            
            with patch('ynab.AccountsApi', return_value=mock_accounts_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_accounts", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    account_data = response_data['accounts'][0]
                    
                    # Verify exact decimal precision is maintained through JSON as strings
                    assert account_data['balance'] == "123456.789"
                    assert account_data['cleared_balance'] == "999999.999"
                    assert account_data['uncleared_balance'] == "0.001"
                    assert account_data['debt_original_balance'] == "-123.001"
                    
                    # Parse back from JSON and verify precision is still maintained
                    balance_decimal = Decimal(account_data['balance'])
                    assert balance_decimal == Decimal('123456.789')
                    
                    cleared_decimal = Decimal(account_data['cleared_balance'])
                    assert cleared_decimal == Decimal('999999.999')
                    
                    uncleared_decimal = Decimal(account_data['uncleared_balance'])
                    assert uncleared_decimal == Decimal('0.001')
                    
                    debt_decimal = Decimal(account_data['debt_original_balance'])
                    assert debt_decimal == Decimal('-123.001')
    
    @pytest.mark.asyncio
    async def test_financial_precision_in_dict_responses(self, mock_env_vars):
        """Test that Decimal precision is maintained in tools that return plain dictionaries."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Test get_budget_month which returns a plain dict
            mock_category = Mock()
            mock_category.id = "cat-precision"
            mock_category.name = "Precision Category"
            mock_category.category_group_id = "group-1"
            mock_category.hidden = False
            mock_category.deleted = False
            mock_category.note = "Test"
            mock_category.budgeted = 123456789  # $123,456.789
            mock_category.activity = -999001    # -$999.001
            mock_category.balance = 1           # $0.001
            mock_category.goal_type = "TB"
            mock_category.goal_target = 500000  # $500.000
            mock_category.goal_percentage_complete = 50
            mock_category.goal_under_funded = 376544  # $376.544
            
            mock_month = Mock()
            mock_month.month = date(2024, 1, 1)  # YNAB returns date, not datetime
            mock_month.note = "Precision test month"
            mock_month.income = 999999999      # $999,999.999
            mock_month.budgeted = 888888888    # $888,888.888
            mock_month.activity = -777777777   # -$777,777.777
            mock_month.to_be_budgeted = 111111 # $111.111
            mock_month.age_of_money = 25
            mock_month.categories = [mock_category]
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    
                    # Verify month-level financial precision
                    assert Decimal(str(response_data['income'])) == Decimal('999999.999')
                    assert Decimal(str(response_data['budgeted'])) == Decimal('888888.888')
                    assert Decimal(str(response_data['activity'])) == Decimal('-777777.777')
                    assert Decimal(str(response_data['to_be_budgeted'])) == Decimal('111.111')
                    
                    # Verify category-level financial precision
                    category_data = response_data['categories'][0]
                    assert Decimal(str(category_data['budgeted'])) == Decimal('123456.789')
                    assert Decimal(str(category_data['activity'])) == Decimal('-999.001')
                    assert Decimal(str(category_data['balance'])) == Decimal('0.001')
                    assert Decimal(str(category_data['goal_target'])) == Decimal('500')
                    assert Decimal(str(category_data['goal_under_funded'])) == Decimal('376.544')
                    
                    # Verify milliunits are preserved as integers
                    assert category_data['budgeted_milliunits'] == 123456789
                    assert category_data['activity_milliunits'] == -999001
                    assert category_data['balance_milliunits'] == 1
    
    @pytest.mark.asyncio
    async def test_date_handling_no_timezone(self, mock_env_vars):
        """Test that date fields are properly handled without timezone information."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock budget with date fields
            mock_budget = Mock()
            mock_budget.id = "budget-date-test"
            mock_budget.name = "Date Test Budget"
            mock_budget.last_modified_on = datetime(2024, 1, 15, 10, 30, 0)  # This should have timezone
            # These should be dates without timezone info  
            mock_budget.first_month = date(2024, 1, 1)  # YNAB returns date objects
            mock_budget.last_month = date(2024, 12, 1)   # YNAB returns date objects
            mock_budget.currency_format = None
            
            mock_response = Mock()
            mock_response.data.budgets = [mock_budget]
            
            mock_budgets_api = Mock()
            mock_budgets_api.get_budgets.return_value = mock_response
            
            with patch('ynab.BudgetsApi', return_value=mock_budgets_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_budgets", {})
                    
                    assert len(result) == 1
                    budget_data = json.loads(result[0].text)
                    
                    # Verify date fields are date strings (YYYY-MM-DD) without time/timezone
                    assert budget_data['first_month'] == '2024-01-01'
                    assert budget_data['last_month'] == '2024-12-01'
                    
                    # Verify these can be parsed as dates without timezone
                    first_month_parsed = date.fromisoformat(budget_data['first_month'])
                    last_month_parsed = date.fromisoformat(budget_data['last_month'])
                    assert first_month_parsed == date(2024, 1, 1)
                    assert last_month_parsed == date(2024, 12, 1)
    
    @pytest.mark.asyncio
    async def test_datetime_handling_with_timezone(self, mock_env_vars):
        """Test that datetime fields properly include timezone information."""
        from datetime import timezone, timedelta
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock with timezone-aware datetime
            utc_datetime = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
            est_datetime = datetime(2024, 2, 20, 15, 45, 30, tzinfo=timezone(timedelta(hours=-5)))
            
            mock_budget = Mock()
            mock_budget.id = "budget-tz-test"
            mock_budget.name = "Timezone Test Budget"
            mock_budget.last_modified_on = utc_datetime
            mock_budget.first_month = None
            mock_budget.last_month = None
            mock_budget.currency_format = None
            
            mock_account = Mock()
            mock_account.id = "acc-tz-test"
            mock_account.name = "TZ Test Account"
            mock_account.type = "checking"
            mock_account.on_budget = True
            mock_account.closed = False
            mock_account.note = None
            mock_account.balance = 100000
            mock_account.cleared_balance = 100000
            mock_account.uncleared_balance = 0
            mock_account.transfer_payee_id = None
            mock_account.direct_import_linked = False
            mock_account.direct_import_in_error = False
            mock_account.last_reconciled_at = est_datetime  # Different timezone
            mock_account.debt_original_balance = None
            
            # Test budget datetime
            mock_budget_response = Mock()
            mock_budget_response.data.budgets = [mock_budget]
            mock_budgets_api = Mock()
            mock_budgets_api.get_budgets.return_value = mock_budget_response
            
            # Test account datetime
            mock_account_response = Mock()
            mock_account_response.data.accounts = [mock_account]
            mock_accounts_api = Mock()
            mock_accounts_api.get_accounts.return_value = mock_account_response
            
            with patch('ynab.BudgetsApi', return_value=mock_budgets_api), \
                 patch('ynab.AccountsApi', return_value=mock_accounts_api):
                
                async with Client(server.mcp) as client:
                    # Test budget datetime
                    budget_result = await client.call_tool("list_budgets", {})
                    budget_data = json.loads(budget_result[0].text)
                    
                    # Verify datetime includes timezone information
                    last_modified = budget_data['last_modified_on']
                    assert last_modified is not None
                    # Should be ISO format with timezone
                    parsed_datetime = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
                    assert parsed_datetime.tzinfo is not None
                    
                    # Test account datetime
                    account_result = await client.call_tool("list_accounts", {})
                    account_data = json.loads(account_result[0].text)
                    account_info = account_data['accounts'][0]
                    
                    # Verify reconciliation datetime has timezone
                    last_reconciled = account_info['last_reconciled_at']
                    assert last_reconciled is not None
                    parsed_reconciled = datetime.fromisoformat(last_reconciled.replace('Z', '+00:00'))
                    assert parsed_reconciled.tzinfo is not None
    
    @pytest.mark.asyncio
    async def test_budget_month_date_vs_datetime_handling(self, mock_env_vars):
        """Test that budget month properly distinguishes between date and datetime fields."""
        from datetime import timezone
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock month with both date and datetime
            mock_month = Mock()
            mock_month.month = date(2024, 3, 1)  # YNAB returns date for month field
            mock_month.note = "March budget"
            mock_month.income = 500000
            mock_month.budgeted = 450000
            mock_month.activity = -300000
            mock_month.to_be_budgeted = 50000
            mock_month.age_of_money = 20
            mock_month.categories = []
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    
                    # Month field should be a date string (YYYY-MM-DD)
                    month_str = response_data['month']
                    assert month_str == '2024-03-01'
                    
                    # Verify it can be parsed as a date (not datetime)
                    parsed_date = date.fromisoformat(month_str)
                    assert parsed_date == date(2024, 3, 1)
                    assert isinstance(parsed_date, date)
                    assert not isinstance(parsed_date, datetime)  # date, not datetime

    @pytest.mark.asyncio
    async def test_get_budget_month_with_literal_strings(self, mock_env_vars):
        """Test get_budget_month with literal string values for month parameter."""
        from datetime import datetime
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock month data
            mock_month = Mock()
            mock_month.month = date(2024, 1, 1)
            mock_month.note = "Test month"
            mock_month.income = 100000
            mock_month.budgeted = 90000
            mock_month.activity = -50000
            mock_month.to_be_budgeted = 10000
            mock_month.age_of_money = 10
            mock_month.categories = []
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api), \
                 patch('server.datetime') as mock_datetime:
                
                # Mock datetime.now() to return a fixed date for consistent testing
                mock_now = datetime(2024, 6, 15, 10, 30, 0)
                mock_datetime.now.return_value = mock_now
                mock_datetime.date = date  # Keep the real date class
                
                async with Client(server.mcp) as client:
                    # Test "current" - should convert to current month date
                    result = await client.call_tool("get_budget_month", {"month": "current"})
                    assert len(result) == 1
                    # Expecting June 1st, 2024 (current month from June 15th)
                    expected_current_month = date(2024, 6, 1)
                    mock_months_api.get_budget_month.assert_called_with("budget-123", expected_current_month)
                    
                    # Test "last" - should convert to previous month's date
                    result = await client.call_tool("get_budget_month", {"month": "last"})
                    assert len(result) == 1
                    # Expecting May 1st, 2024 (previous month from June 15th)
                    expected_last_month = date(2024, 5, 1)
                    mock_months_api.get_budget_month.assert_called_with("budget-123", expected_last_month)
                    
                    # Test "next" - should convert to next month's date  
                    result = await client.call_tool("get_budget_month", {"month": "next"})
                    assert len(result) == 1
                    # Expecting July 1st, 2024 (next month from June 15th)
                    expected_next_month = date(2024, 7, 1)
                    mock_months_api.get_budget_month.assert_called_with("budget-123", expected_next_month)

    @pytest.mark.asyncio
    async def test_get_budget_month_with_date_object(self, mock_env_vars):
        """Test get_budget_month with actual date object for month parameter."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock month data
            mock_month = Mock()
            mock_month.month = date(2024, 3, 1)
            mock_month.note = "March test"
            mock_month.income = 150000
            mock_month.budgeted = 140000
            mock_month.activity = -80000
            mock_month.to_be_budgeted = 10000
            mock_month.age_of_money = 15
            mock_month.categories = []
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    # Test with date object - FastMCP should convert to ISO string
                    test_date = date(2024, 3, 1)
                    result = await client.call_tool("get_budget_month", {"month": test_date})
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert response_data['note'] == "March test"
                    # The YNAB API receives the date as ISO string 
                    mock_months_api.get_budget_month.assert_called_with("budget-123", test_date)

    @pytest.mark.asyncio
    async def test_get_month_category_by_id_with_literal_strings(self, mock_env_vars):
        """Test get_month_category_by_id with literal string values for month parameter."""
        from datetime import datetime
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            mock_category = Mock()
            mock_category.id = "cat-123"
            mock_category.name = "Test Category"
            mock_category.category_group_id = "group-1"
            mock_category.hidden = False
            mock_category.note = "Test note"
            mock_category.budgeted = 50000
            mock_category.activity = -30000
            mock_category.balance = 20000
            mock_category.goal_type = "TB"
            mock_category.goal_target = 100000
            mock_category.goal_percentage_complete = 50
            mock_category.goal_under_funded = 0
            
            mock_response = Mock()
            mock_response.data.category = mock_category
            
            mock_months_api = Mock()
            mock_months_api.get_month_category_by_id.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api), \
                 patch('server.datetime') as mock_datetime:
                
                # Mock datetime.now() to return a fixed date for consistent testing
                mock_now = datetime(2024, 8, 20, 14, 45, 0)
                mock_datetime.now.return_value = mock_now
                mock_datetime.date = date  # Keep the real date class
                
                async with Client(server.mcp) as client:
                    # Test "current" - should convert to current month date
                    result = await client.call_tool("get_month_category_by_id", {
                        "budget_id": "budget-123",
                        "category_id": "cat-123",
                        "month": "current"
                    })
                    assert len(result) == 1
                    # Expecting August 1st, 2024 (current month from August 20th)
                    expected_current_month = date(2024, 8, 1)
                    mock_months_api.get_month_category_by_id.assert_called_with("budget-123", expected_current_month, "cat-123")
                    
                    # Test "last" - should convert to previous month's date
                    result = await client.call_tool("get_month_category_by_id", {
                        "budget_id": "budget-123",
                        "category_id": "cat-123",
                        "month": "last"
                    })
                    assert len(result) == 1
                    # Expecting July 1st, 2024 (previous month from August 20th)
                    expected_last_month = date(2024, 7, 1)
                    mock_months_api.get_month_category_by_id.assert_called_with("budget-123", expected_last_month, "cat-123")
                    
                    # Test "next" - should convert to next month's date
                    result = await client.call_tool("get_month_category_by_id", {
                        "budget_id": "budget-123",
                        "category_id": "cat-123",
                        "month": "next"
                    })
                    assert len(result) == 1
                    # Expecting September 1st, 2024 (next month from August 20th)
                    expected_next_month = date(2024, 9, 1)
                    mock_months_api.get_month_category_by_id.assert_called_with("budget-123", expected_next_month, "cat-123")

    @pytest.mark.asyncio
    async def test_get_month_category_by_id_with_date_object(self, mock_env_vars):
        """Test get_month_category_by_id with actual date object for month parameter."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            mock_category = Mock()
            mock_category.id = "cat-456"
            mock_category.name = "Date Test Category"
            mock_category.category_group_id = "group-2"
            mock_category.hidden = False
            mock_category.note = "Date test"
            mock_category.budgeted = 75000
            mock_category.activity = -45000
            mock_category.balance = 30000
            mock_category.goal_type = "TBD"
            mock_category.goal_target = 150000
            mock_category.goal_percentage_complete = 75
            mock_category.goal_under_funded = 0
            
            mock_response = Mock()
            mock_response.data.category = mock_category
            
            mock_months_api = Mock()
            mock_months_api.get_month_category_by_id.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    # Test with date object
                    test_date = date(2024, 6, 1)
                    result = await client.call_tool("get_month_category_by_id", {
                        "budget_id": "budget-456",
                        "category_id": "cat-456",
                        "month": test_date
                    })
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert response_data['id'] == "cat-456"
                    assert response_data['name'] == "Date Test Category"
                    # The YNAB API receives the date as passed
                    mock_months_api.get_month_category_by_id.assert_called_with("budget-456", test_date, "cat-456")

