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
            
            server.get_ynab_client()
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

    def test_budget_id_or_default_with_value(self):
        """Test budget_id_or_default returns provided value when not None."""
        result = server.budget_id_or_default("custom-budget-123")
        assert result == "custom-budget-123"

    def test_budget_id_or_default_with_none(self, monkeypatch):
        """Test budget_id_or_default returns default when None."""
        monkeypatch.setenv("YNAB_DEFAULT_BUDGET", "default-budget-456")
        result = server.budget_id_or_default(None)
        assert result == "default-budget-456"

    def test_budget_id_or_default_with_none_missing_env(self, monkeypatch):
        """Test budget_id_or_default raises error when None and no env var."""
        monkeypatch.delenv("YNAB_DEFAULT_BUDGET", raising=False)
        with pytest.raises(ValueError, match="budget_id is required"):
            server.budget_id_or_default(None)

    def test_convert_transaction_to_model_basic(self):
        """Test convert_transaction_to_model with basic transaction."""
        from unittest.mock import Mock
        
        mock_txn = Mock()
        mock_txn.id = "txn-123"
        mock_txn.var_date = date(2024, 6, 15)
        mock_txn.amount = -50000
        mock_txn.memo = "Test transaction"
        mock_txn.cleared = "cleared"
        mock_txn.approved = True
        mock_txn.flag_color = "red"
        mock_txn.account_id = "acc-1"
        mock_txn.payee_id = "payee-1"
        mock_txn.category_id = "cat-1"
        mock_txn.transfer_account_id = None
        mock_txn.transfer_transaction_id = None
        mock_txn.matched_transaction_id = None
        mock_txn.import_id = None
        mock_txn.import_payee_name = None
        mock_txn.import_payee_name_original = None
        mock_txn.debt_transaction_type = None
        mock_txn.deleted = False
        mock_txn.subtransactions = None
        
        # Test with attributes present (TransactionDetail)
        mock_txn.account_name = "Checking"
        mock_txn.payee_name = "Test Payee"
        mock_txn.category_name = "Test Category"
        
        result = server.convert_transaction_to_model(mock_txn)
        
        assert result.id == "txn-123"
        assert result.date == date(2024, 6, 15)
        assert result.amount == Decimal("-50")
        assert result.account_name == "Checking"
        assert result.payee_name == "Test Payee"
        assert result.category_name == "Test Category"
        assert result.subtransactions is None

    def test_convert_transaction_to_model_without_optional_attributes(self):
        """Test convert_transaction_to_model with HybridTransaction (missing some attributes)."""
        from unittest.mock import Mock
        
        mock_txn = Mock()
        mock_txn.id = "txn-456"
        mock_txn.var_date = date(2024, 6, 16)
        mock_txn.amount = -25000
        mock_txn.memo = "Hybrid transaction"
        mock_txn.cleared = "uncleared"
        mock_txn.approved = True
        mock_txn.flag_color = None
        mock_txn.account_id = "acc-2"
        mock_txn.payee_id = "payee-2"
        mock_txn.category_id = "cat-2"
        mock_txn.transfer_account_id = None
        mock_txn.transfer_transaction_id = None
        mock_txn.matched_transaction_id = None
        mock_txn.import_id = None
        mock_txn.import_payee_name = None
        mock_txn.import_payee_name_original = None
        mock_txn.debt_transaction_type = None
        mock_txn.deleted = False
        
        # HybridTransaction doesn't have these attributes
        del mock_txn.account_name
        del mock_txn.payee_name  
        del mock_txn.category_name
        del mock_txn.subtransactions
        
        result = server.convert_transaction_to_model(mock_txn)
        
        assert result.id == "txn-456"
        assert result.account_name is None
        assert result.payee_name is None
        assert result.category_name is None
        assert result.subtransactions is None


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("YNAB_ACCESS_TOKEN", "test_token_123")
    monkeypatch.setenv("YNAB_DEFAULT_BUDGET", "budget-123")


class TestMCPTools:
    """Test all MCP tools using FastMCP testing patterns with real YNAB models."""
    
    @pytest.mark.asyncio
    async def test_list_budgets_success(self, mock_env_vars):
        """Test successful budget listing using real YNAB models."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create budget with currency format using real YNAB models
            currency_format = ynab.CurrencyFormat(
                iso_code="USD",
                example_format="$123.45",
                decimal_digits=2,
                decimal_separator=".",
                symbol_first=True,
                group_separator=",",
                currency_symbol="$",
                display_symbol=True
            )
            
            test_budget = ynab.BudgetSummary(
                id="budget-123",
                name="Test Budget",
                last_modified_on=None,
                first_month=None,
                last_month=None,
                date_format=None,
                currency_format=currency_format,
                accounts=None
            )
            
            budgets_response = ynab.BudgetSummaryResponse(
                data=ynab.BudgetSummaryResponseData(budgets=[test_budget])
            )
            mock_budgets_api = Mock()
            mock_budgets_api.get_budgets.return_value = budgets_response
            
            with patch('ynab.BudgetsApi', return_value=mock_budgets_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_budgets", {})
                    
                    assert len(result) == 1
                    # The result is a list of Budget objects serialized as JSON
                    budgets_data = json.loads(result[0].text)
                    # budgets_data is a single Budget object, not a list
                    assert budgets_data['id'] == "budget-123"
                    assert budgets_data['name'] == "Test Budget"
                    assert budgets_data['currency_format']['iso_code'] == "USD"

    @pytest.mark.asyncio
    async def test_list_budgets_null_currency(self, mock_env_vars):
        """Test budget listing with null currency format using real YNAB models."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create budget with null currency using real YNAB model
            test_budget = ynab.BudgetSummary(
                id="budget-456",
                name="Budget No Currency", 
                last_modified_on=None,
                first_month=None,
                last_month=None,
                date_format=None,
                currency_format=None,
                accounts=None
            )
            
            budgets_response = ynab.BudgetSummaryResponse(
                data=ynab.BudgetSummaryResponseData(budgets=[test_budget])
            )
            mock_budgets_api = Mock()
            mock_budgets_api.get_budgets.return_value = budgets_response
            
            with patch('ynab.BudgetsApi', return_value=mock_budgets_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_budgets", {})
                    
                    assert len(result) == 1
                    budgets_data = json.loads(result[0].text)
                    assert budgets_data['id'] == "budget-456"
                    assert budgets_data['currency_format'] is None

    @pytest.mark.asyncio
    async def test_list_accounts_success(self, mock_env_vars):
        """Test successful account listing using real YNAB models."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create accounts using real YNAB models
            open_account = ynab.Account(
                id="acc-1",
                name="Checking",
                type="checking",
                on_budget=True,
                closed=False,
                note="Main account",
                balance=100000,  # $100.00
                cleared_balance=95000,
                uncleared_balance=5000,
                transfer_payee_id="payee-1",
                direct_import_linked=True,
                direct_import_in_error=False,
                last_reconciled_at=datetime(2024, 1, 10, 9, 0, 0),
                debt_original_balance=None,
                debt_interest_rates=None,
                debt_minimum_payments=None,
                debt_escrow_amounts=None,
                deleted=False
            )
            
            closed_account = ynab.Account(
                id="acc-2",
                name="Savings",
                type="savings",
                on_budget=False,
                closed=True,  # Closed account - should be excluded
                note=None,
                balance=0,
                cleared_balance=0,
                uncleared_balance=0,
                transfer_payee_id=None,
                direct_import_linked=False,
                direct_import_in_error=False,
                last_reconciled_at=None,
                debt_original_balance=None,
                debt_interest_rates=None,
                debt_minimum_payments=None,
                debt_escrow_amounts=None,
                deleted=False
            )
            
            accounts_response = ynab.AccountsResponse(
                data=ynab.AccountsResponseData(accounts=[open_account, closed_account], server_knowledge=0)
            )
            mock_accounts_api = Mock()
            mock_accounts_api.get_accounts.return_value = accounts_response
            
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
    async def test_list_categories_success(self, mock_env_vars):
        """Test successful category listing using real YNAB models."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create categories using real YNAB models
            visible_category = ynab.Category(
                id="cat-1",
                category_group_id="group-1",
                category_group_name="Monthly Bills",
                name="Groceries",
                hidden=False,
                original_category_group_id=None,
                note="Food shopping",
                budgeted=50000,
                activity=-30000,
                balance=20000,
                goal_type="TB",
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=100000,
                goal_target_month=None,
                goal_percentage_complete=50,
                goal_months_to_budget=None,
                goal_under_funded=0,
                goal_overall_funded=None,
                goal_overall_left=None,
                deleted=False
            )
            
            hidden_category = ynab.Category(
                id="cat-hidden",
                category_group_id="group-1",
                category_group_name="Monthly Bills",
                name="Hidden Category",
                hidden=True,  # Should be excluded by default
                original_category_group_id=None,
                note=None,
                budgeted=10000,
                activity=0,
                balance=10000,
                goal_type=None,
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=None,
                goal_target_month=None,
                goal_percentage_complete=None,
                goal_months_to_budget=None,
                goal_under_funded=None,
                goal_overall_funded=None,
                goal_overall_left=None,
                deleted=False
            )
            
            category_group = ynab.CategoryGroupWithCategories(
                id="group-1",
                name="Monthly Bills",
                hidden=False,
                deleted=False,
                categories=[visible_category, hidden_category]
            )
            
            categories_response = ynab.CategoriesResponse(
                data=ynab.CategoriesResponseData(category_groups=[category_group], server_knowledge=0)
            )
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = categories_response
            
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
    async def test_get_month_category_by_id_default_budget(self, mock_env_vars):
        """Test month category retrieval using default budget ID."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create category using real YNAB model
            test_category = ynab.Category(
                id="cat-default",
                category_group_id="group-1",
                category_group_name="Default Group",
                name="Default Category",
                hidden=False,
                original_category_group_id=None,
                note="Using default budget",
                budgeted=25000,
                activity=-15000,
                balance=10000,
                goal_type="TB",
                goal_needs_whole_amount=None,
                goal_day=None,
                goal_cadence=None,
                goal_cadence_frequency=None,
                goal_creation_month=None,
                goal_target=50000,
                goal_target_month=None,
                goal_percentage_complete=50,
                goal_months_to_budget=None,
                goal_under_funded=0,
                goal_overall_funded=None,
                goal_overall_left=None,
                deleted=False
            )
            
            category_response = ynab.CategoryResponse(
                data=ynab.CategoryResponseData(category=test_category, server_knowledge=0)
            )
            mock_months_api = Mock()
            mock_months_api.get_month_category_by_id.return_value = category_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    # Call without budget_id to trigger get_default_budget_id() - this covers line 475
                    result = await client.call_tool("get_month_category_by_id", {
                        "category_id": "cat-default"
                    })
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert response_data['id'] == "cat-default"
                    assert response_data['name'] == "Default Category"
                    assert response_data['note'] == "Using default budget"




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

    @pytest.mark.asyncio
    async def test_list_transactions_basic(self, mock_env_vars):
        """Test basic transaction listing without filters."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create transactions using real YNAB models
            txn1 = ynab.TransactionDetail(
                id="txn-1",
                var_date=date(2024, 1, 15),
                amount=-50000,  # -$50.00 outflow
                memo="Grocery shopping",
                cleared="cleared",
                approved=True,
                flag_color="red",
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-1",
                payee_name="Whole Foods",
                category_id="cat-1",
                category_name="Groceries",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            txn2 = ynab.TransactionDetail(
                id="txn-2",
                var_date=date(2024, 1, 20),
                amount=-75000,  # -$75.00 outflow
                memo="Dinner",
                cleared="uncleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-2",
                payee_name="Restaurant XYZ",
                category_id="cat-2",
                category_name="Dining Out",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            # Add a deleted transaction that should be filtered out
            txn_deleted = ynab.TransactionDetail(
                id="txn-deleted",
                var_date=date(2024, 1, 10),
                amount=-25000,
                memo="Deleted transaction",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-3",
                payee_name="Store ABC",
                category_id="cat-1",
                category_name="Groceries",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=True,  # Should be excluded
                subtransactions=[]
            )
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=[txn2, txn1, txn_deleted],  # Out of order to test sorting
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_transactions", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    
                    # Should have 2 transactions (deleted one excluded)
                    assert len(response_data['transactions']) == 2
                    
                    # Should be sorted by date descending
                    assert response_data['transactions'][0]['id'] == "txn-2"
                    assert response_data['transactions'][0]['date'] == "2024-01-20"
                    assert response_data['transactions'][0]['amount'] == "-75"
                    assert response_data['transactions'][0]['payee_name'] == "Restaurant XYZ"
                    assert response_data['transactions'][0]['category_name'] == "Dining Out"
                    
                    assert response_data['transactions'][1]['id'] == "txn-1"
                    assert response_data['transactions'][1]['date'] == "2024-01-15"
                    assert response_data['transactions'][1]['amount'] == "-50"
                    assert response_data['transactions'][1]['flag_color'] == "red"
                    
                    # Check pagination
                    assert response_data['pagination']['total_count'] == 2
                    assert response_data['pagination']['has_more'] == False
                    assert response_data['pagination']['returned_count'] == 2

    @pytest.mark.asyncio
    async def test_list_transactions_with_account_filter(self, mock_env_vars):
        """Test transaction listing filtered by account."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create transaction
            txn = ynab.TransactionDetail(
                id="txn-acc-1",
                var_date=date(2024, 2, 1),
                amount=-30000,
                memo="Account filtered",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-checking",
                account_name="Main Checking",
                payee_id="payee-1",
                payee_name="Store",
                category_id="cat-1",
                category_name="Shopping",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=[txn],
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions_by_account.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_transactions", {
                        "account_id": "acc-checking"
                    })
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert len(response_data['transactions']) == 1
                    assert response_data['transactions'][0]['account_id'] == "acc-checking"
                    
                    # Verify correct API method was called
                    mock_transactions_api.get_transactions_by_account.assert_called_once()
                    args = mock_transactions_api.get_transactions_by_account.call_args[0]
                    assert args[1] == "acc-checking"  # account_id parameter

    @pytest.mark.asyncio
    async def test_list_transactions_with_amount_filters(self, mock_env_vars):
        """Test transaction listing with amount range filters."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create transactions with different amounts
            txn_small = ynab.TransactionDetail(
                id="txn-small",
                var_date=date(2024, 3, 1),
                amount=-25000,  # -$25
                memo="Small purchase",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-1",
                payee_name="Coffee Shop",
                category_id="cat-1",
                category_name="Dining Out",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            txn_medium = ynab.TransactionDetail(
                id="txn-medium",
                var_date=date(2024, 3, 2),
                amount=-60000,  # -$60
                memo="Medium purchase",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-2",
                payee_name="Restaurant",
                category_id="cat-1",
                category_name="Dining Out",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            txn_large = ynab.TransactionDetail(
                id="txn-large",
                var_date=date(2024, 3, 3),
                amount=-120000,  # -$120
                memo="Large purchase",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-3",
                payee_name="Electronics Store",
                category_id="cat-2",
                category_name="Shopping",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=[txn_small, txn_medium, txn_large],
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    # Test with min_amount filter (transactions >= -$50)
                    result = await client.call_tool("list_transactions", {
                        "min_amount": -50.0  # -$50
                    })
                    
                    response_data = json.loads(result[0].text)
                    # Should only include small transaction (-$25 > -$50)
                    assert len(response_data['transactions']) == 1
                    assert response_data['transactions'][0]['id'] == "txn-small"
                    
                    # Test with max_amount filter (transactions <= -$100)
                    result = await client.call_tool("list_transactions", {
                        "max_amount": -100.0  # -$100
                    })
                    
                    response_data = json.loads(result[0].text)
                    # Should only include large transaction (-$120 < -$100)
                    assert len(response_data['transactions']) == 1
                    assert response_data['transactions'][0]['id'] == "txn-large"
                    
                    # Test with both min and max filters
                    result = await client.call_tool("list_transactions", {
                        "min_amount": -80.0,  # >= -$80
                        "max_amount": -40.0   # <= -$40
                    })
                    
                    response_data = json.loads(result[0].text)
                    # Should only include medium transaction (-$60)
                    assert len(response_data['transactions']) == 1
                    assert response_data['transactions'][0]['id'] == "txn-medium"

    @pytest.mark.asyncio
    async def test_list_transactions_with_subtransactions(self, mock_env_vars):
        """Test transaction listing with split transactions (subtransactions)."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create subtransactions
            sub1 = ynab.SubTransaction(
                id="sub-1",
                transaction_id="txn-split",
                amount=-30000,  # -$30
                memo="Groceries portion",
                payee_id=None,
                payee_name=None,
                category_id="cat-groceries",
                category_name="Groceries",
                transfer_account_id=None,
                transfer_transaction_id=None,
                deleted=False
            )
            
            sub2 = ynab.SubTransaction(
                id="sub-2",
                transaction_id="txn-split",
                amount=-20000,  # -$20
                memo="Household items",
                payee_id=None,
                payee_name=None,
                category_id="cat-household",
                category_name="Household",
                transfer_account_id=None,
                transfer_transaction_id=None,
                deleted=False
            )
            
            # Deleted subtransaction should be filtered out
            sub_deleted = ynab.SubTransaction(
                id="sub-deleted",
                transaction_id="txn-split",
                amount=-10000,
                memo="Deleted sub",
                payee_id=None,
                payee_name=None,
                category_id="cat-other",
                category_name="Other",
                transfer_account_id=None,
                transfer_transaction_id=None,
                deleted=True
            )
            
            # Create split transaction
            txn_split = ynab.TransactionDetail(
                id="txn-split",
                var_date=date(2024, 4, 1),
                amount=-50000,  # -$50 total
                memo="Split transaction at Target",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-target",
                payee_name="Target",
                category_id=None,  # Split transactions don't have a single category
                category_name=None,
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[sub1, sub2, sub_deleted]
            )
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=[txn_split],
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_transactions", {})
                    
                    response_data = json.loads(result[0].text)
                    assert len(response_data['transactions']) == 1
                    
                    txn = response_data['transactions'][0]
                    assert txn['id'] == "txn-split"
                    assert txn['amount'] == "-50"
                    
                    # Should have 2 subtransactions (deleted one excluded)
                    assert len(txn['subtransactions']) == 2
                    assert txn['subtransactions'][0]['id'] == "sub-1"
                    assert txn['subtransactions'][0]['amount'] == "-30"
                    assert txn['subtransactions'][0]['category_name'] == "Groceries"
                    assert txn['subtransactions'][1]['id'] == "sub-2"
                    assert txn['subtransactions'][1]['amount'] == "-20"
                    assert txn['subtransactions'][1]['category_name'] == "Household"

    @pytest.mark.asyncio
    async def test_list_transactions_pagination(self, mock_env_vars):
        """Test transaction listing with pagination."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create many transactions to test pagination
            transactions = []
            for i in range(5):
                txn = ynab.TransactionDetail(
                    id=f"txn-{i}",
                    var_date=date(2024, 1, i + 1),
                    amount=-10000 * (i + 1),
                    memo=f"Transaction {i}",
                    cleared="cleared",
                    approved=True,
                    flag_color=None,
                    account_id="acc-1",
                    account_name="Checking",
                    payee_id=f"payee-{i}",
                    payee_name=f"Store {i}",
                    category_id="cat-1",
                    category_name="Shopping",
                    transfer_account_id=None,
                    transfer_transaction_id=None,
                    matched_transaction_id=None,
                    import_id=None,
                    import_payee_name=None,
                    import_payee_name_original=None,
                    debt_transaction_type=None,
                    deleted=False,
                    subtransactions=[]
                )
                transactions.append(txn)
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=transactions,
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    # Test first page
                    result = await client.call_tool("list_transactions", {
                        "limit": 2,
                        "offset": 0
                    })
                    
                    response_data = json.loads(result[0].text)
                    assert len(response_data['transactions']) == 2
                    assert response_data['pagination']['total_count'] == 5
                    assert response_data['pagination']['has_more'] == True
                    assert response_data['pagination']['next_offset'] == 2
                    assert response_data['pagination']['returned_count'] == 2
                    
                    # Transactions should be sorted by date descending
                    assert response_data['transactions'][0]['id'] == "txn-4"
                    assert response_data['transactions'][1]['id'] == "txn-3"
                    
                    # Test second page
                    result = await client.call_tool("list_transactions", {
                        "limit": 2,
                        "offset": 2
                    })
                    
                    response_data = json.loads(result[0].text)
                    assert len(response_data['transactions']) == 2
                    assert response_data['transactions'][0]['id'] == "txn-2"
                    assert response_data['transactions'][1]['id'] == "txn-1"

    @pytest.mark.asyncio
    async def test_list_transactions_with_category_filter(self, mock_env_vars):
        """Test transaction listing filtered by category."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create transaction
            txn = ynab.TransactionDetail(
                id="txn-cat-1",
                var_date=date(2024, 2, 1),
                amount=-40000,
                memo="Category filtered",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-1",
                payee_name="Store",
                category_id="cat-dining",
                category_name="Dining Out",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=[txn],
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions_by_category.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_transactions", {
                        "category_id": "cat-dining"
                    })
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert len(response_data['transactions']) == 1
                    assert response_data['transactions'][0]['category_id'] == "cat-dining"
                    
                    # Verify correct API method was called
                    mock_transactions_api.get_transactions_by_category.assert_called_once()
                    args = mock_transactions_api.get_transactions_by_category.call_args[0]
                    assert args[1] == "cat-dining"  # category_id parameter

    @pytest.mark.asyncio
    async def test_list_transactions_with_payee_filter(self, mock_env_vars):
        """Test transaction listing filtered by payee."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create transaction
            txn = ynab.TransactionDetail(
                id="txn-payee-1",
                var_date=date(2024, 3, 1),
                amount=-80000,
                memo="Payee filtered",
                cleared="cleared",
                approved=True,
                flag_color=None,
                account_id="acc-1",
                account_name="Checking",
                payee_id="payee-amazon",
                payee_name="Amazon",
                category_id="cat-shopping",
                category_name="Shopping",
                transfer_account_id=None,
                transfer_transaction_id=None,
                matched_transaction_id=None,
                import_id=None,
                import_payee_name=None,
                import_payee_name_original=None,
                debt_transaction_type=None,
                deleted=False,
                subtransactions=[]
            )
            
            transactions_response = ynab.TransactionsResponse(
                data=ynab.TransactionsResponseData(
                    transactions=[txn],
                    server_knowledge=0
                )
            )
            
            mock_transactions_api = Mock()
            mock_transactions_api.get_transactions_by_payee.return_value = transactions_response
            
            with patch('ynab.TransactionsApi', return_value=mock_transactions_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_transactions", {
                        "payee_id": "payee-amazon"
                    })
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    assert len(response_data['transactions']) == 1
                    assert response_data['transactions'][0]['payee_id'] == "payee-amazon"
                    
                    # Verify correct API method was called
                    mock_transactions_api.get_transactions_by_payee.assert_called_once()
                    args = mock_transactions_api.get_transactions_by_payee.call_args[0]
                    assert args[1] == "payee-amazon"  # payee_id parameter

    @pytest.mark.asyncio
    async def test_list_payees_success(self, mock_env_vars):
        """Test successful payee listing using real YNAB models."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create payees using real YNAB models
            payee1 = ynab.Payee(
                id="payee-1",
                name="Amazon",
                transfer_account_id=None,
                deleted=False
            )
            
            payee2 = ynab.Payee(
                id="payee-2", 
                name="Whole Foods",
                transfer_account_id=None,
                deleted=False
            )
            
            # Deleted payee should be excluded by default
            payee_deleted = ynab.Payee(
                id="payee-deleted",
                name="Closed Store",
                transfer_account_id=None,
                deleted=True
            )
            
            # Transfer payee
            payee_transfer = ynab.Payee(
                id="payee-transfer",
                name="Transfer : Savings",
                transfer_account_id="acc-savings",
                deleted=False
            )
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=[payee2, payee1, payee_deleted, payee_transfer],  # Not sorted
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_payees", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    
                    # Should have 3 payees (deleted one excluded)
                    assert len(response_data['payees']) == 3
                    
                    # Should be sorted by name
                    assert response_data['payees'][0]['name'] == "Amazon"
                    assert response_data['payees'][1]['name'] == "Transfer : Savings"
                    assert response_data['payees'][2]['name'] == "Whole Foods"
                    
                    # Check transfer payee details
                    transfer_payee = response_data['payees'][1]
                    assert transfer_payee['id'] == "payee-transfer"
                    assert transfer_payee['transfer_account_id'] == "acc-savings"
                    
                    # Check pagination
                    assert response_data['pagination']['total_count'] == 3
                    assert response_data['pagination']['has_more'] == False


    @pytest.mark.asyncio
    async def test_list_payees_pagination(self, mock_env_vars):
        """Test payee listing with pagination."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create multiple payees
            payees = []
            for i in range(5):
                payee = ynab.Payee(
                    id=f"payee-{i}",
                    name=f"Store {i:02d}",  # Store 00, Store 01, etc. for predictable sorting
                    transfer_account_id=None,
                    deleted=False
                )
                payees.append(payee)
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=payees,
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    # Test first page
                    result = await client.call_tool("list_payees", {
                        "limit": 2,
                        "offset": 0
                    })
                    
                    response_data = json.loads(result[0].text)
                    assert len(response_data['payees']) == 2
                    assert response_data['pagination']['total_count'] == 5
                    assert response_data['pagination']['has_more'] == True
                    assert response_data['pagination']['next_offset'] == 2
                    
                    # Should be sorted alphabetically
                    assert response_data['payees'][0]['name'] == "Store 00"
                    assert response_data['payees'][1]['name'] == "Store 01"

    @pytest.mark.asyncio
    async def test_list_categories_filters_deleted_and_hidden(self, mock_env_vars):
        """Test that list_categories automatically filters out deleted and hidden categories."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create mock category group with mix of categories
            mock_category_group = Mock()
            mock_category_group.name = "Monthly Bills"
            
            # Active category (should be included)
            import ynab
            mock_active_category = ynab.Category(
                id="cat-active",
                name="Active Category",
                category_group_id="group-1",
                hidden=False,
                deleted=False,
                note="Active",
                budgeted=10000,
                activity=-5000,
                balance=5000,
                goal_type=None,
                goal_target=None,
                goal_percentage_complete=None,
                goal_under_funded=None,
                goal_creation_month=None,
                goal_target_month=None,
                goal_overall_funded=None,
                goal_overall_left=None
            )
            
            # Hidden category (should be excluded)
            mock_hidden_category = ynab.Category(
                id="cat-hidden",
                name="Hidden Category",
                category_group_id="group-1",
                hidden=True,
                deleted=False,
                note="Hidden",
                budgeted=0,
                activity=0,
                balance=0,
                goal_type=None,
                goal_target=None,
                goal_percentage_complete=None,
                goal_under_funded=None,
                goal_creation_month=None,
                goal_target_month=None,
                goal_overall_funded=None,
                goal_overall_left=None
            )
            
            # Deleted category (should be excluded)
            mock_deleted_category = ynab.Category(
                id="cat-deleted",
                name="Deleted Category",
                category_group_id="group-1",
                hidden=False,
                deleted=True,
                note="Deleted",
                budgeted=0,
                activity=0,
                balance=0,
                goal_type=None,
                goal_target=None,
                goal_percentage_complete=None,
                goal_under_funded=None,
                goal_creation_month=None,
                goal_target_month=None,
                goal_overall_funded=None,
                goal_overall_left=None
            )
            
            mock_category_group.categories = [mock_active_category, mock_hidden_category, mock_deleted_category]
            
            mock_response = Mock()
            mock_response.data.category_groups = [mock_category_group]
            
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = mock_response
            
            with patch('ynab.CategoriesApi', return_value=mock_categories_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_categories", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should only include the active category
                    assert len(response_data['categories']) == 1
                    assert response_data['categories'][0]['id'] == "cat-active"
                    assert response_data['categories'][0]['name'] == "Active Category"

    @pytest.mark.asyncio
    async def test_list_category_groups_filters_deleted(self, mock_env_vars):
        """Test that list_category_groups automatically filters out deleted groups."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Active group (should be included)
            mock_active_group = Mock()
            mock_active_group.id = "group-active"
            mock_active_group.name = "Active Group"
            mock_active_group.hidden = False
            mock_active_group.deleted = False
            mock_active_group.categories = []
            
            # Deleted group (should be excluded)
            mock_deleted_group = Mock()
            mock_deleted_group.id = "group-deleted"
            mock_deleted_group.name = "Deleted Group"
            mock_deleted_group.hidden = False
            mock_deleted_group.deleted = True
            mock_deleted_group.categories = []
            
            mock_response = Mock()
            mock_response.data.category_groups = [mock_active_group, mock_deleted_group]
            
            mock_categories_api = Mock()
            mock_categories_api.get_categories.return_value = mock_response
            
            with patch('ynab.CategoriesApi', return_value=mock_categories_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_category_groups", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should only include the active group (returns single group object when filtered to one)
                    assert response_data['id'] == "group-active"
                    assert response_data['name'] == "Active Group"

    @pytest.mark.asyncio
    async def test_get_budget_month_filters_deleted_and_hidden(self, mock_env_vars):
        """Test that get_budget_month automatically filters out deleted and hidden categories."""
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Active category (should be included)
            import ynab
            mock_active_category = ynab.Category(
                id="cat-active",
                name="Active Category",
                category_group_id="group-1",
                hidden=False,
                deleted=False,
                note="Active",
                budgeted=10000,
                activity=-5000,
                balance=5000,
                goal_type=None,
                goal_target=None,
                goal_percentage_complete=None,
                goal_under_funded=None,
                goal_creation_month=None,
                goal_target_month=None,
                goal_overall_funded=None,
                goal_overall_left=None
            )
            
            # Hidden category (should be excluded)
            mock_hidden_category = ynab.Category(
                id="cat-hidden",
                name="Hidden Category",
                category_group_id="group-1",
                hidden=True,
                deleted=False,
                note="Hidden",
                budgeted=0,
                activity=0,
                balance=0,
                goal_type=None,
                goal_target=None,
                goal_percentage_complete=None,
                goal_under_funded=None,
                goal_creation_month=None,
                goal_target_month=None,
                goal_overall_funded=None,
                goal_overall_left=None
            )
            
            mock_month = Mock()
            mock_month.month = date(2024, 1, 1)
            mock_month.note = "January budget"
            mock_month.income = 400000
            mock_month.budgeted = 350000
            mock_month.activity = -200000
            mock_month.to_be_budgeted = 50000
            mock_month.age_of_money = 15
            # Deleted category (should be excluded)
            mock_deleted_category = ynab.Category(
                id="cat-deleted",
                name="Deleted Category",
                category_group_id="group-1",
                hidden=False,
                deleted=True,
                note="Deleted",
                budgeted=0,
                activity=0,
                balance=0,
                goal_type=None,
                goal_target=None,
                goal_percentage_complete=None,
                goal_under_funded=None,
                goal_creation_month=None,
                goal_target_month=None,
                goal_overall_funded=None,
                goal_overall_left=None
            )
            
            mock_month.categories = [mock_active_category, mock_hidden_category, mock_deleted_category]
            
            mock_response = Mock()
            mock_response.data.month = mock_month
            
            mock_months_api = Mock()
            mock_months_api.get_budget_month.return_value = mock_response
            
            with patch('ynab.MonthsApi', return_value=mock_months_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("get_budget_month", {})
                    
                    assert len(result) == 1
                    response_data = json.loads(result[0].text)
                    # Should only include the active category
                    assert len(response_data['categories']) == 1
                    assert response_data['categories'][0]['id'] == "cat-active"
                    assert response_data['categories'][0]['name'] == "Active Category"

    @pytest.mark.asyncio
    async def test_list_payees_filters_deleted(self, mock_env_vars):
        """Test that list_payees automatically filters out deleted payees."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Active payee (should be included)
            payee_active = ynab.Payee(
                id="payee-active",
                name="Active Store",
                transfer_account_id=None,
                deleted=False
            )
            
            # Deleted payee (should be excluded)
            payee_deleted = ynab.Payee(
                id="payee-deleted",
                name="Deleted Store",
                transfer_account_id=None,
                deleted=True
            )
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=[payee_active, payee_deleted],
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("list_payees", {})
                    
                    response_data = json.loads(result[0].text)
                    # Should only include the active payee
                    assert len(response_data['payees']) == 1
                    assert response_data['payees'][0]['name'] == "Active Store"
                    assert response_data['payees'][0]['id'] == "payee-active"

    @pytest.mark.asyncio
    async def test_find_payee_filters_deleted(self, mock_env_vars):
        """Test that find_payee automatically filters out deleted payees."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Both payees have "amazon" in name, but one is deleted
            payee_active = ynab.Payee(
                id="payee-active",
                name="Amazon",
                transfer_account_id=None,
                deleted=False
            )
            
            payee_deleted = ynab.Payee(
                id="payee-deleted",
                name="Amazon Prime",
                transfer_account_id=None,
                deleted=True
            )
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=[payee_active, payee_deleted],
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("find_payee", {
                        "name_search": "amazon"
                    })
                    
                    response_data = json.loads(result[0].text)
                    # Should only find the active Amazon payee, not the deleted one
                    assert len(response_data['payees']) == 1
                    assert response_data['payees'][0]['name'] == "Amazon"
                    assert response_data['payees'][0]['id'] == "payee-active"

    @pytest.mark.asyncio
    async def test_find_payee_success(self, mock_env_vars):
        """Test successful payee search by name."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create payees with different names for searching
            payees = [
                ynab.Payee(
                    id="payee-amazon",
                    name="Amazon",
                    transfer_account_id=None,
                    deleted=False
                ),
                ynab.Payee(
                    id="payee-amazon-web",
                    name="Amazon Web Services",
                    transfer_account_id=None,
                    deleted=False
                ),
                ynab.Payee(
                    id="payee-starbucks",
                    name="Starbucks",
                    transfer_account_id=None,
                    deleted=False
                ),
                ynab.Payee(
                    id="payee-grocery",
                    name="Whole Foods Market",
                    transfer_account_id=None,
                    deleted=False
                ),
                ynab.Payee(
                    id="payee-deleted",
                    name="Amazon Prime",
                    transfer_account_id=None,
                    deleted=True
                )
            ]
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=payees,
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    # Test searching for "amazon" (case-insensitive)
                    result = await client.call_tool("find_payee", {
                        "name_search": "amazon"
                    })
                    
                    response_data = json.loads(result[0].text)
                    # Should find Amazon and Amazon Web Services, but not deleted Amazon Prime
                    assert len(response_data['payees']) == 2
                    assert response_data['pagination']['total_count'] == 2
                    assert response_data['pagination']['has_more'] == False
                    
                    # Should be sorted alphabetically
                    payee_names = [p['name'] for p in response_data['payees']]
                    assert payee_names == ["Amazon", "Amazon Web Services"]

    @pytest.mark.asyncio
    async def test_find_payee_case_insensitive(self, mock_env_vars):
        """Test that payee search is case-insensitive."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            payees = [
                ynab.Payee(
                    id="payee-1",
                    name="Starbucks Coffee",
                    transfer_account_id=None,
                    deleted=False
                )
            ]
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=payees,
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    # Test various case combinations
                    search_terms_matches = [
                        ("STARBUCKS", 1),
                        ("starbucks", 1),
                        ("StArBuCkS", 1),
                        ("coffee", 1),
                        ("COFFEE", 1),
                        ("nonexistent", 0)  # This will test the else branch
                    ]
                    
                    for search_term, expected_count in search_terms_matches:
                        result = await client.call_tool("find_payee", {
                            "name_search": search_term
                        })
                        
                        response_data = json.loads(result[0].text)
                        assert len(response_data['payees']) == expected_count
                        if expected_count > 0:
                            assert response_data['payees'][0]['name'] == "Starbucks Coffee"


    @pytest.mark.asyncio
    async def test_find_payee_limit(self, mock_env_vars):
        """Test payee search with limit parameter."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            # Create multiple payees with "store" in the name
            payees = []
            for i in range(5):
                payees.append(
                    ynab.Payee(
                        id=f"payee-{i}",
                        name=f"Store {i:02d}",  # Store 00, Store 01, etc.
                        transfer_account_id=None,
                        deleted=False
                    )
                )
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=payees,
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    # Test with limit of 2
                    result = await client.call_tool("find_payee", {
                        "name_search": "store",
                        "limit": 2
                    })
                    
                    response_data = json.loads(result[0].text)
                    assert len(response_data['payees']) == 2
                    assert response_data['pagination']['total_count'] == 5
                    assert response_data['pagination']['has_more'] == True
                    assert response_data['pagination']['returned_count'] == 2
                    
                    # Should be first 2 in alphabetical order
                    assert response_data['payees'][0]['name'] == "Store 00"
                    assert response_data['payees'][1]['name'] == "Store 01"

    @pytest.mark.asyncio
    async def test_find_payee_no_matches(self, mock_env_vars):
        """Test payee search with no matching results."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            payees = [
                ynab.Payee(
                    id="payee-1",
                    name="Starbucks",
                    transfer_account_id=None,
                    deleted=False
                )
            ]
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=payees,
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                async with Client(server.mcp) as client:
                    result = await client.call_tool("find_payee", {
                        "name_search": "nonexistent"
                    })
                    
                    response_data = json.loads(result[0].text)
                    assert len(response_data['payees']) == 0
                    assert response_data['pagination']['total_count'] == 0
                    assert response_data['pagination']['has_more'] == False
                    assert response_data['pagination']['returned_count'] == 0

    @pytest.mark.asyncio
    async def test_find_payee_budget_id_or_default(self, mock_env_vars):
        """Test find_payee uses budget_id_or_default helper."""
        import ynab
        
        with patch('server.get_ynab_client') as mock_get_client:
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.__exit__.return_value = None
            mock_get_client.return_value = mock_client
            
            payees_response = ynab.PayeesResponse(
                data=ynab.PayeesResponseData(
                    payees=[],
                    server_knowledge=1000
                )
            )
            
            mock_payees_api = Mock()
            mock_payees_api.get_payees.return_value = payees_response
            
            with patch('ynab.PayeesApi', return_value=mock_payees_api):
                with patch('server.budget_id_or_default') as mock_budget_helper:
                    mock_budget_helper.return_value = "default-budget-123"
                    
                    async with Client(server.mcp) as client:
                        await client.call_tool("find_payee", {
                            "name_search": "test"
                        })
                        
                        # Should call the helper with None
                        mock_budget_helper.assert_called_once_with(None)
                        # Should call the API with the returned budget ID
                        mock_payees_api.get_payees.assert_called_once_with("default-budget-123")


