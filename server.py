import os
from typing import List, Dict, Any, Optional
from datetime import date, datetime
import ynab
from fastmcp import FastMCP

from models import (
    Budget, Account, Category, CategoryGroup, BudgetMonth,
    CurrencyFormat, PaginationInfo,
    BudgetsResponse, AccountsResponse, CategoriesResponse, CategoryGroupsResponse
)

# Initialize FastMCP server
mcp = FastMCP("YNAB MCP Server")

def get_ynab_client():
    """Get authenticated YNAB client"""
    access_token = os.getenv("YNAB_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("YNAB_ACCESS_TOKEN environment variable is required")
    
    configuration = ynab.Configuration(access_token=access_token)
    return ynab.ApiClient(configuration)

def milliunits_to_currency(milliunits: int, decimal_digits: int = 2) -> float:
    """Convert YNAB milliunits to currency amount
    
    YNAB uses milliunits where 1000 milliunits = 1 currency unit
    """
    if milliunits is None:
        return None
    return milliunits / 1000.0

def get_default_budget_id() -> str:
    """Get default budget ID from environment variable or raise error"""
    budget_id = os.getenv("YNAB_DEFAULT_BUDGET")
    if not budget_id:
        raise ValueError("budget_id is required or set YNAB_DEFAULT_BUDGET environment variable")
    return budget_id

@mcp.tool()
def list_budgets() -> List[Budget]:
    """List all budgets from YNAB with metadata and currency formatting information."""
    with get_ynab_client() as api_client:
        budgets_api = ynab.BudgetsApi(api_client)
        budgets_response = budgets_api.get_budgets()
        
        budgets = []
        for budget in budgets_response.data.budgets:
            currency_format = None
            if budget.currency_format:
                currency_format = CurrencyFormat(
                    iso_code=budget.currency_format.iso_code,
                    example_format=budget.currency_format.example_format,
                    decimal_digits=budget.currency_format.decimal_digits,
                    decimal_separator=budget.currency_format.decimal_separator,
                    symbol_first=budget.currency_format.symbol_first,
                    group_separator=budget.currency_format.group_separator,
                    currency_symbol=budget.currency_format.currency_symbol,
                    display_symbol=budget.currency_format.display_symbol
                )
            
            budgets.append(Budget(
                id=budget.id,
                name=budget.name,
                last_modified_on=budget.last_modified_on.isoformat() if budget.last_modified_on else None,
                first_month=budget.first_month.isoformat() if budget.first_month else None,
                last_month=budget.last_month.isoformat() if budget.last_month else None,
                currency_format=currency_format
            ))
        
        return budgets

@mcp.tool()
def list_accounts(budget_id: str = None, limit: int = 100, offset: int = 0, include_closed: bool = False) -> AccountsResponse:
    """List accounts for a specific budget with pagination and filtering options.
    
    Args:
        budget_id: Budget ID (uses YNAB_DEFAULT_BUDGET if not provided)
        limit: Maximum number of accounts to return (default 100)
        offset: Number of accounts to skip (default 0)
        include_closed: Whether to include closed accounts (default False)
    
    Returns:
        AccountsResponse with accounts list and pagination information
    """
    if budget_id is None:
        budget_id = get_default_budget_id()
    
    with get_ynab_client() as api_client:
        accounts_api = ynab.AccountsApi(api_client)
        accounts_response = accounts_api.get_accounts(budget_id)
        
        # Filter accounts
        all_accounts = []
        for account in accounts_response.data.accounts:
            # Skip closed accounts unless requested
            if account.closed and not include_closed:
                continue
                
            all_accounts.append(Account(
                id=account.id,
                name=account.name,
                type=account.type,
                on_budget=account.on_budget,
                closed=account.closed,
                note=account.note,
                balance=milliunits_to_currency(account.balance),
                cleared_balance=milliunits_to_currency(account.cleared_balance),
                uncleared_balance=milliunits_to_currency(account.uncleared_balance),
                transfer_payee_id=account.transfer_payee_id,
                direct_import_linked=account.direct_import_linked,
                direct_import_in_error=account.direct_import_in_error,
                last_reconciled_at=account.last_reconciled_at.isoformat() if account.last_reconciled_at else None,
                debt_original_balance=milliunits_to_currency(account.debt_original_balance)
            ))
        
        # Apply pagination
        total_count = len(all_accounts)
        start_index = offset
        end_index = min(offset + limit, total_count)
        accounts_page = all_accounts[start_index:end_index]
        
        has_more = end_index < total_count
        next_offset = end_index if has_more else None
        
        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(accounts_page)
        )
        
        return AccountsResponse(accounts=accounts_page, pagination=pagination)

@mcp.tool()
def list_categories(budget_id: str = None, limit: int = 50, offset: int = 0, include_hidden: bool = False) -> Dict[str, Any]:
    """List categories for a specific budget with pagination and filtering options.
    
    Args:
        budget_id: Budget ID (uses YNAB_DEFAULT_BUDGET if not provided)
        limit: Maximum number of categories to return (default 50)
        offset: Number of categories to skip (default 0)
        include_hidden: Whether to include hidden categories (default False)
    
    Returns:
        Dict with 'categories', 'total_count', 'has_more', 'next_offset' fields
    """
    if budget_id is None:
        budget_id = get_default_budget_id()
    
    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)
        
        # First, collect all eligible categories
        all_categories = []
        for category_group in categories_response.data.category_groups:
            for category in category_group.categories:
                # Skip hidden categories unless requested
                if category.hidden and not include_hidden:
                    continue
                    
                # Skip deleted categories
                if category.deleted:
                    continue
                
                all_categories.append({
                    "id": category.id,
                    "name": category.name,
                    "category_group_id": category.category_group_id,
                    "category_group_name": category_group.name,
                    "hidden": category.hidden,
                    "note": category.note,
                    "budgeted": milliunits_to_currency(category.budgeted),
                    "activity": milliunits_to_currency(category.activity),
                    "balance": milliunits_to_currency(category.balance),
                    "goal_type": category.goal_type,
                    "goal_target": milliunits_to_currency(category.goal_target),
                    "goal_percentage_complete": category.goal_percentage_complete,
                    "goal_under_funded": milliunits_to_currency(category.goal_under_funded)
                })
        
        # Apply pagination
        total_count = len(all_categories)
        start_index = offset
        end_index = min(offset + limit, total_count)
        categories_page = all_categories[start_index:end_index]
        
        has_more = end_index < total_count
        next_offset = end_index if has_more else None
        
        return {
            "categories": categories_page,
            "pagination": {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "returned_count": len(categories_page)
            }
        }

@mcp.tool()
def list_category_groups(budget_id: str = None) -> List[Dict[str, Any]]:
    """List category groups for a specific budget (lighter weight than full categories)."""
    if budget_id is None:
        budget_id = get_default_budget_id()
    
    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)
        
        groups = []
        for category_group in categories_response.data.category_groups:
            if category_group.deleted:
                continue
                
            # Calculate totals for the group (exclude deleted and hidden categories)
            total_budgeted = sum(cat.budgeted or 0 for cat in category_group.categories if not cat.deleted and not cat.hidden)
            total_activity = sum(cat.activity or 0 for cat in category_group.categories if not cat.deleted and not cat.hidden)
            total_balance = sum(cat.balance or 0 for cat in category_group.categories if not cat.deleted and not cat.hidden)
            
            groups.append({
                "id": category_group.id,
                "name": category_group.name,
                "hidden": category_group.hidden,
                "category_count": len([cat for cat in category_group.categories if not cat.deleted and not cat.hidden]),
                "total_budgeted": milliunits_to_currency(total_budgeted),
                "total_activity": milliunits_to_currency(total_activity),
                "total_balance": milliunits_to_currency(total_balance)
            })
        
        return groups

@mcp.tool()
def get_budget_month(budget_id: str = None, month: str = "current", limit: int = 50, offset: int = 0, include_hidden: bool = False) -> Dict[str, Any]:
    """Get budget data for a specific month including category budgets, activity, and balances with pagination.
    
    Args:
        budget_id: Budget ID (uses YNAB_DEFAULT_BUDGET if not provided)
        month: Month in ISO format (YYYY-MM-DD) or "current" (default "current")
        limit: Maximum number of categories to return (default 50)
        offset: Number of categories to skip (default 0)
        include_hidden: Whether to include hidden categories (default False)
    
    Returns:
        Dict with month info, categories with budgeted/activity/balance data, and pagination info
    """
    if budget_id is None:
        budget_id = get_default_budget_id()
    
    with get_ynab_client() as api_client:
        months_api = ynab.MonthsApi(api_client)
        month_response = months_api.get_budget_month(budget_id, month)
        
        month_data = month_response.data.month
        all_categories = []
        
        for category in month_data.categories:
            if category.deleted:
                continue
            
            # Skip hidden categories unless requested
            if category.hidden and not include_hidden:
                continue
                
            all_categories.append({
                "id": category.id,
                "name": category.name,
                "category_group_id": category.category_group_id,
                "hidden": category.hidden,
                "note": category.note,
                "budgeted": milliunits_to_currency(category.budgeted),
                "activity": milliunits_to_currency(category.activity),
                "balance": milliunits_to_currency(category.balance),
                "goal_type": category.goal_type,
                "goal_target": milliunits_to_currency(category.goal_target),
                "goal_percentage_complete": category.goal_percentage_complete,
                "goal_under_funded": milliunits_to_currency(category.goal_under_funded),
                "budgeted_milliunits": category.budgeted,
                "activity_milliunits": category.activity,
                "balance_milliunits": category.balance
            })
        
        # Apply pagination
        total_count = len(all_categories)
        start_index = offset
        end_index = min(offset + limit, total_count)
        categories_page = all_categories[start_index:end_index]
        
        has_more = end_index < total_count
        next_offset = end_index if has_more else None
        
        return {
            "month": month_data.month.isoformat() if month_data.month else None,
            "note": month_data.note,
            "income": milliunits_to_currency(month_data.income),
            "budgeted": milliunits_to_currency(month_data.budgeted),
            "activity": milliunits_to_currency(month_data.activity),
            "to_be_budgeted": milliunits_to_currency(month_data.to_be_budgeted),
            "age_of_money": month_data.age_of_money,
            "categories": categories_page,
            "income_milliunits": month_data.income,
            "budgeted_milliunits": month_data.budgeted,
            "activity_milliunits": month_data.activity,
            "to_be_budgeted_milliunits": month_data.to_be_budgeted,
            "pagination": {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "returned_count": len(categories_page)
            }
        }

@mcp.tool()
def get_month_category_by_id(budget_id: str, category_id: str, month: str = "current") -> Dict[str, Any]:
    """Get a specific category's data for a specific month.
    
    Args:
        budget_id: Budget ID (required)
        category_id: Category ID (required)
        month: Month in ISO format (YYYY-MM-DD) or "current" (default "current")
    
    Returns:
        Dict with category budget data for the specified month
    """
    with get_ynab_client() as api_client:
        months_api = ynab.MonthsApi(api_client)
        category_response = months_api.get_month_category_by_id(budget_id, month, category_id)
        
        category = category_response.data.category
        
        return {
            "id": category.id,
            "name": category.name,
            "category_group_id": category.category_group_id,
            "hidden": category.hidden,
            "note": category.note,
            "budgeted": milliunits_to_currency(category.budgeted),
            "activity": milliunits_to_currency(category.activity),
            "balance": milliunits_to_currency(category.balance),
            "goal_type": category.goal_type,
            "goal_target": milliunits_to_currency(category.goal_target),
            "goal_percentage_complete": category.goal_percentage_complete,
            "goal_under_funded": milliunits_to_currency(category.goal_under_funded),
            "budgeted_milliunits": category.budgeted,
            "activity_milliunits": category.activity,
            "balance_milliunits": category.balance
        }

if __name__ == "__main__":
    print("Starting YNAB MCP Server...")
    print("Make sure to set your YNAB_ACCESS_TOKEN environment variable")
    mcp.run()
