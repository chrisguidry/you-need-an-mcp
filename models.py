"""
Pydantic models for YNAB MCP Server responses.

These models provide structured, well-documented data types for all YNAB API responses,
including detailed explanations of YNAB's data model subtleties and conventions.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class CurrencyFormat(BaseModel):
    """YNAB currency formatting information for proper display of amounts."""

    iso_code: str = Field(
        ..., description="ISO 4217 currency code (e.g., 'USD', 'EUR')"
    )
    example_format: str = Field(
        ..., description="Example of how currency should be formatted (e.g., '$123.45')"
    )
    decimal_digits: int = Field(
        ..., description="Number of decimal places for this currency"
    )
    decimal_separator: str = Field(
        ..., description="Character used for decimal separation (e.g., '.')"
    )
    symbol_first: bool = Field(
        ..., description="Whether currency symbol appears before the amount"
    )
    group_separator: str = Field(
        ..., description="Character used for thousands separation (e.g., ',')"
    )
    currency_symbol: str = Field(..., description="Currency symbol (e.g., '$', '€')")
    display_symbol: bool = Field(
        ..., description="Whether to display the currency symbol"
    )


class Budget(BaseModel):
    """A YNAB budget with metadata and currency information."""

    id: str = Field(..., description="Unique budget identifier")
    name: str = Field(..., description="User-defined budget name")
    last_modified_on: Optional[datetime.datetime] = Field(
        None, description="Timestamp of last modification (UTC)"
    )
    first_month: Optional[datetime.date] = Field(
        None, description="First month available in this budget"
    )
    last_month: Optional[datetime.date] = Field(
        None, description="Last month available in this budget"
    )
    currency_format: Optional[CurrencyFormat] = Field(
        None, description="Currency formatting rules for this budget"
    )


class PaginationInfo(BaseModel):
    """Pagination metadata for listing endpoints."""

    total_count: int = Field(..., description="Total number of items available")
    limit: int = Field(..., description="Maximum items requested per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(
        ..., description="Whether more items are available beyond this page"
    )
    next_offset: Optional[int] = Field(
        None, description="Offset to use for next page (null if no more pages)"
    )
    returned_count: int = Field(
        ..., description="Actual number of items returned in this page"
    )


class Account(BaseModel):
    """A YNAB account with balance information.

    Note: All balance amounts are provided in both milliunits (YNAB's internal format where
    1000 milliunits = 1 currency unit) and converted currency amounts using Decimal for precision.
    """

    id: str = Field(..., description="Unique account identifier")
    name: str = Field(..., description="User-defined account name")
    type: str = Field(
        ..., description="Account type (e.g., 'checking', 'savings', 'creditCard')"
    )
    on_budget: bool = Field(
        ..., description="Whether this account is included in budget calculations"
    )
    closed: bool = Field(..., description="Whether this account has been closed")
    note: Optional[str] = Field(None, description="User-defined account notes")
    balance: Optional[Decimal] = Field(
        None, description="Current account balance in currency units"
    )
    cleared_balance: Optional[Decimal] = Field(
        None, description="Balance of cleared transactions in currency units"
    )
    uncleared_balance: Optional[Decimal] = Field(
        None, description="Balance of uncleared transactions in currency units"
    )
    transfer_payee_id: Optional[str] = Field(
        None, description="ID of the payee used for transfers to this account"
    )
    direct_import_linked: Optional[bool] = Field(
        None, description="Whether account is linked for direct import"
    )
    direct_import_in_error: Optional[bool] = Field(
        None, description="Whether direct import is currently in error state"
    )
    last_reconciled_at: Optional[datetime.datetime] = Field(
        None, description="Timestamp of last reconciliation (UTC)"
    )
    debt_original_balance: Optional[Decimal] = Field(
        None, description="Original balance for debt accounts in currency units"
    )


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
    category_group_id: str = Field(
        ..., description="ID of the category group this category belongs to"
    )
    category_group_name: Optional[str] = Field(
        None, description="Name of the category group (included in list_categories)"
    )
    hidden: bool = Field(
        ..., description="Whether this category is hidden from normal budget view"
    )
    note: Optional[str] = Field(None, description="User-defined category notes")
    budgeted: Optional[Decimal] = Field(
        None, description="Amount budgeted for this category in currency units"
    )
    activity: Optional[Decimal] = Field(
        None,
        description="Total spending activity (negative = spending, positive = income)",
    )
    balance: Optional[Decimal] = Field(
        None, description="Available balance (budgeted + activity)"
    )
    goal_type: Optional[str] = Field(
        None, description="Type of goal set for this category (NEED, TB, TBD, MF)"
    )
    goal_target: Optional[Decimal] = Field(
        None, description="Target amount for the goal in currency units"
    )
    goal_percentage_complete: Optional[int] = Field(
        None, description="Percentage of goal completed (0-100)"
    )
    goal_under_funded: Optional[Decimal] = Field(
        None, description="Amount still needed to meet goal in currency units"
    )
    budgeted_milliunits: Optional[int] = Field(
        None,
        description="Raw budgeted amount in YNAB milliunits (1000 = 1 currency unit)",
    )
    activity_milliunits: Optional[int] = Field(
        None, description="Raw activity amount in YNAB milliunits"
    )
    balance_milliunits: Optional[int] = Field(
        None, description="Raw balance amount in YNAB milliunits"
    )


class CategoryGroup(BaseModel):
    """A YNAB category group with summary totals.

    Category groups organize related categories together (e.g., 'Monthly Bills', 'Everyday Expenses').
    The totals include all non-deleted categories within the group.
    """

    id: str = Field(..., description="Unique category group identifier")
    name: str = Field(..., description="User-defined category group name")
    hidden: bool = Field(
        ..., description="Whether this category group is hidden from normal budget view"
    )
    category_count: int = Field(
        ..., description="Number of non-deleted categories in this group"
    )
    total_budgeted: Optional[Decimal] = Field(
        None, description="Sum of budgeted amounts for all categories in this group"
    )
    total_activity: Optional[Decimal] = Field(
        None, description="Sum of activity for all categories in this group"
    )
    total_balance: Optional[Decimal] = Field(
        None, description="Sum of balances for all categories in this group"
    )


class BudgetMonth(BaseModel):
    """Monthly budget summary with category details.

    Provides complete monthly budget information including income, total budgeted amounts,
    spending activity, and detailed category breakdowns.
    """

    month: Optional[datetime.date] = Field(None, description="Budget month date")
    note: Optional[str] = Field(
        None, description="User-defined notes for this budget month"
    )
    income: Optional[Decimal] = Field(
        None, description="Total income for the month in currency units"
    )
    budgeted: Optional[Decimal] = Field(
        None, description="Total amount budgeted across all categories"
    )
    activity: Optional[Decimal] = Field(
        None, description="Total spending activity for the month"
    )
    to_be_budgeted: Optional[Decimal] = Field(
        None, description="Amount remaining to be budgeted (can be negative)"
    )
    age_of_money: Optional[int] = Field(
        None,
        description="Age of money in days (how long money sits before being spent)",
    )
    categories: List[Category] = Field(
        ..., description="List of categories with their monthly budget data"
    )
    income_milliunits: Optional[int] = Field(
        None, description="Raw income amount in YNAB milliunits"
    )
    budgeted_milliunits: Optional[int] = Field(
        None, description="Raw budgeted amount in YNAB milliunits"
    )
    activity_milliunits: Optional[int] = Field(
        None, description="Raw activity amount in YNAB milliunits"
    )
    to_be_budgeted_milliunits: Optional[int] = Field(
        None, description="Raw to-be-budgeted amount in YNAB milliunits"
    )
    pagination: Optional[PaginationInfo] = Field(
        None, description="Pagination information for category list"
    )


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

    categories: List[Category] = Field(
        ..., description="List of category structures (no budget amounts)"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")


class CategoryGroupsResponse(BaseModel):
    """Response model for list_category_groups tool."""

    category_groups: List[CategoryGroup] = Field(
        ..., description="List of category groups with totals"
    )


class Subtransaction(BaseModel):
    """A subtransaction within a split transaction.

    Subtransactions allow a single transaction to be split across multiple categories.
    The parent transaction's amount must equal the sum of all subtransaction amounts.
    """

    id: str = Field(..., description="Unique subtransaction identifier")
    transaction_id: str = Field(..., description="Parent transaction ID")
    amount: Decimal = Field(..., description="Subtransaction amount in currency units")
    memo: Optional[str] = Field(None, description="Subtransaction-specific memo")
    payee_id: Optional[str] = Field(
        None, description="Payee ID (if different from parent)"
    )
    payee_name: Optional[str] = Field(None, description="Payee name")
    category_id: Optional[str] = Field(None, description="Category ID for this portion")
    category_name: Optional[str] = Field(None, description="Category name")
    transfer_account_id: Optional[str] = Field(
        None, description="If a transfer, the account ID"
    )
    transfer_transaction_id: Optional[str] = Field(
        None, description="If a transfer, the transaction ID"
    )
    deleted: bool = Field(..., description="Whether subtransaction has been deleted")
    amount_milliunits: Optional[int] = Field(
        None, description="Raw amount in YNAB milliunits"
    )


class Transaction(BaseModel):
    """A YNAB transaction with full details.

    Transactions represent money moving in or out of accounts. Amounts are negative for outflows
    (spending) and positive for inflows (income/deposits).

    Flag colors can be: 'red', 'orange', 'yellow', 'green', 'blue', 'purple', or null.
    Cleared status can be: 'cleared', 'uncleared', or 'reconciled'.
    """

    id: str = Field(..., description="Unique transaction identifier")
    date: datetime.date = Field(..., description="Transaction date")
    amount: Decimal = Field(
        ...,
        description="Transaction amount in currency units (negative = outflow, positive = inflow)",
    )
    memo: Optional[str] = Field(None, description="User-entered memo/notes")
    cleared: str = Field(
        ..., description="Cleared status: 'cleared', 'uncleared', or 'reconciled'"
    )
    approved: bool = Field(
        ...,
        description="Whether transaction is approved (false if imported and awaiting approval)",
    )
    flag_color: Optional[str] = Field(
        None,
        description="Flag color: 'red', 'orange', 'yellow', 'green', 'blue', 'purple', or null",
    )
    account_id: str = Field(..., description="Account ID where transaction occurred")
    account_name: Optional[str] = Field(
        None, description="Account name (included when listing transactions)"
    )
    payee_id: Optional[str] = Field(
        None, description="Payee ID (who transaction was with)"
    )
    payee_name: Optional[str] = Field(
        None, description="Payee name (included when listing transactions)"
    )
    category_id: Optional[str] = Field(
        None, description="Category ID (null for transfers or uncategorized)"
    )
    category_name: Optional[str] = Field(
        None, description="Category name (included when listing transactions)"
    )
    transfer_account_id: Optional[str] = Field(
        None, description="If a transfer, the account ID of the other side"
    )
    transfer_transaction_id: Optional[str] = Field(
        None, description="If a transfer, the transaction ID of the other side"
    )
    matched_transaction_id: Optional[str] = Field(
        None, description="If matched to another transaction during import"
    )
    import_id: Optional[str] = Field(
        None, description="Import ID for deduplication during imports"
    )
    import_payee_name: Optional[str] = Field(
        None, description="Original payee name from import before mapping"
    )
    import_payee_name_original: Optional[str] = Field(
        None, description="Original payee name before any YNAB modifications"
    )
    debt_transaction_type: Optional[str] = Field(
        None,
        description="For debt accounts: 'payment', 'refund', 'fee', 'interest', etc.",
    )
    deleted: bool = Field(..., description="Whether transaction has been deleted")
    amount_milliunits: Optional[int] = Field(
        None, description="Raw amount in YNAB milliunits (1000 = 1 currency unit)"
    )

    # Subtransactions for split transactions
    subtransactions: Optional[List[Subtransaction]] = Field(
        None, description="Subtransactions for split transactions"
    )


class TransactionsResponse(BaseModel):
    """Response model for list_transactions tool."""

    transactions: List[Transaction] = Field(
        ..., description="List of transactions matching filters"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")


class Payee(BaseModel):
    """A YNAB payee (person, company, or entity that receives payments).
    
    Payees can be manually created or automatically created when transactions are imported.
    Transfer payees are special system-generated payees for account transfers.
    """

    id: str = Field(..., description="Unique payee identifier")
    name: str = Field(..., description="Payee name")
    transfer_account_id: Optional[str] = Field(
        None, description="If this is a transfer payee, the associated account ID"
    )
    deleted: bool = Field(..., description="Whether payee has been deleted")


class PayeesResponse(BaseModel):
    """Response model for list_payees tool."""

    payees: List[Payee] = Field(..., description="List of payees in the budget")
    pagination: PaginationInfo = Field(..., description="Pagination information")
