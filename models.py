"""
Pydantic models for YNAB MCP Server responses.

These models provide structured, well-documented data types for all YNAB API responses,
including detailed explanations of YNAB's data model subtleties and conventions.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CurrencyFormat(BaseModel):
    """YNAB currency formatting information for proper display of amounts."""
    iso_code: str = Field(..., description="ISO 4217 currency code (e.g., 'USD', 'EUR')")
    example_format: str = Field(..., description="Example of how currency should be formatted (e.g., '$123.45')")
    decimal_digits: int = Field(..., description="Number of decimal places for this currency")
    decimal_separator: str = Field(..., description="Character used for decimal separation (e.g., '.')")
    symbol_first: bool = Field(..., description="Whether currency symbol appears before the amount")
    group_separator: str = Field(..., description="Character used for thousands separation (e.g., ',')")
    currency_symbol: str = Field(..., description="Currency symbol (e.g., '$', '€')")
    display_symbol: bool = Field(..., description="Whether to display the currency symbol")


class Budget(BaseModel):
    """A YNAB budget with metadata and currency information."""
    id: str = Field(..., description="Unique budget identifier")
    name: str = Field(..., description="User-defined budget name")
    last_modified_on: Optional[str] = Field(None, description="ISO 8601 timestamp of last modification (UTC)")
    first_month: Optional[str] = Field(None, description="First month available in this budget (YYYY-MM-DD)")
    last_month: Optional[str] = Field(None, description="Last month available in this budget (YYYY-MM-DD)")
    currency_format: Optional[CurrencyFormat] = Field(None, description="Currency formatting rules for this budget")


class PaginationInfo(BaseModel):
    """Pagination metadata for listing endpoints."""
    total_count: int = Field(..., description="Total number of items available")
    limit: int = Field(..., description="Maximum items requested per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(..., description="Whether more items are available beyond this page")
    next_offset: Optional[int] = Field(None, description="Offset to use for next page (null if no more pages)")
    returned_count: int = Field(..., description="Actual number of items returned in this page")


class Account(BaseModel):
    """A YNAB account with balance information.
    
    Note: All balance amounts are provided in both milliunits (YNAB's internal format where 
    1000 milliunits = 1 currency unit) and converted currency amounts for convenience.
    """
    id: str = Field(..., description="Unique account identifier")
    name: str = Field(..., description="User-defined account name")
    type: str = Field(..., description="Account type (e.g., 'checking', 'savings', 'creditCard')")
    on_budget: bool = Field(..., description="Whether this account is included in budget calculations")
    closed: bool = Field(..., description="Whether this account has been closed")
    note: Optional[str] = Field(None, description="User-defined account notes")
    balance: Optional[float] = Field(None, description="Current account balance in currency units")
    cleared_balance: Optional[float] = Field(None, description="Balance of cleared transactions in currency units")
    uncleared_balance: Optional[float] = Field(None, description="Balance of uncleared transactions in currency units")
    transfer_payee_id: Optional[str] = Field(None, description="ID of the payee used for transfers to this account")
    direct_import_linked: Optional[bool] = Field(None, description="Whether account is linked for direct import")
    direct_import_in_error: Optional[bool] = Field(None, description="Whether direct import is currently in error state")
    last_reconciled_at: Optional[str] = Field(None, description="ISO 8601 timestamp of last reconciliation (UTC)")
    debt_original_balance: Optional[float] = Field(None, description="Original balance for debt accounts in currency units")


class Category(BaseModel):
    """A YNAB category with budget and goal information.
    
    Categories can have different goal types that affect how YNAB handles monthly budgeting:
    - 'NEED': Set aside specific amount each month
    - 'TB': Target Balance - work toward a specific balance
    - 'TBD': Target Balance by Date - reach balance by specific date
    - 'MF': Monthly Funding - budget same amount each month
    """
    id: str = Field(..., description="Unique category identifier")
    name: str = Field(..., description="User-defined category name")
    category_group_id: str = Field(..., description="ID of the category group this category belongs to")
    category_group_name: Optional[str] = Field(None, description="Name of the category group (included in list_categories)")
    hidden: bool = Field(..., description="Whether this category is hidden from normal budget view")
    note: Optional[str] = Field(None, description="User-defined category notes")
    budgeted: Optional[float] = Field(None, description="Amount budgeted for this category in currency units")
    activity: Optional[float] = Field(None, description="Total spending activity (negative = spending, positive = income)")
    balance: Optional[float] = Field(None, description="Available balance (budgeted + activity)")
    goal_type: Optional[str] = Field(None, description="Type of goal set for this category (NEED, TB, TBD, MF)")
    goal_target: Optional[float] = Field(None, description="Target amount for the goal in currency units")
    goal_percentage_complete: Optional[int] = Field(None, description="Percentage of goal completed (0-100)")
    goal_under_funded: Optional[float] = Field(None, description="Amount still needed to meet goal in currency units")
    budgeted_milliunits: Optional[int] = Field(None, description="Raw budgeted amount in YNAB milliunits (1000 = 1 currency unit)")
    activity_milliunits: Optional[int] = Field(None, description="Raw activity amount in YNAB milliunits")
    balance_milliunits: Optional[int] = Field(None, description="Raw balance amount in YNAB milliunits")


class CategoryGroup(BaseModel):
    """A YNAB category group with summary totals.
    
    Category groups organize related categories together (e.g., 'Monthly Bills', 'Everyday Expenses').
    The totals include all non-deleted categories within the group.
    """
    id: str = Field(..., description="Unique category group identifier")
    name: str = Field(..., description="User-defined category group name")
    hidden: bool = Field(..., description="Whether this category group is hidden from normal budget view")
    category_count: int = Field(..., description="Number of non-deleted categories in this group")
    total_budgeted: Optional[float] = Field(None, description="Sum of budgeted amounts for all categories in this group")
    total_activity: Optional[float] = Field(None, description="Sum of activity for all categories in this group")
    total_balance: Optional[float] = Field(None, description="Sum of balances for all categories in this group")


class BudgetMonth(BaseModel):
    """Monthly budget summary with category details.
    
    Provides complete monthly budget information including income, total budgeted amounts,
    spending activity, and detailed category breakdowns.
    """
    month: Optional[str] = Field(None, description="Budget month in YYYY-MM-DD format")
    note: Optional[str] = Field(None, description="User-defined notes for this budget month")
    income: Optional[float] = Field(None, description="Total income for the month in currency units")
    budgeted: Optional[float] = Field(None, description="Total amount budgeted across all categories")
    activity: Optional[float] = Field(None, description="Total spending activity for the month")
    to_be_budgeted: Optional[float] = Field(None, description="Amount remaining to be budgeted (can be negative)")
    age_of_money: Optional[int] = Field(None, description="Age of money in days (how long money sits before being spent)")
    categories: List[Category] = Field(..., description="List of categories with their monthly budget data")
    income_milliunits: Optional[int] = Field(None, description="Raw income amount in YNAB milliunits")
    budgeted_milliunits: Optional[int] = Field(None, description="Raw budgeted amount in YNAB milliunits")
    activity_milliunits: Optional[int] = Field(None, description="Raw activity amount in YNAB milliunits")
    to_be_budgeted_milliunits: Optional[int] = Field(None, description="Raw to-be-budgeted amount in YNAB milliunits")
    pagination: Optional[PaginationInfo] = Field(None, description="Pagination information for category list")


# Response models for MCP tools
class BudgetsResponse(BaseModel):
    """Response model for list_budgets tool."""
    budgets: List[Budget] = Field(..., description="List of available YNAB budgets")


class AccountsResponse(BaseModel):
    """Response model for list_accounts tool."""
    accounts: List[Account] = Field(..., description="List of accounts in the budget")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class CategoriesResponse(BaseModel):
    """Response model for list_categories tool (structure only, no budget amounts)."""
    categories: List[Category] = Field(..., description="List of category structures (no budget amounts)")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class CategoryGroupsResponse(BaseModel):
    """Response model for list_category_groups tool."""
    category_groups: List[CategoryGroup] = Field(..., description="List of category groups with totals")