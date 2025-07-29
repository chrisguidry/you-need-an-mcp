"""
Pydantic models for YNAB MCP Server responses.

These models provide structured, well-documented data types for all YNAB API responses,
including detailed explanations of YNAB's data model subtleties and conventions.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import ynab
from pydantic import BaseModel, Field


def milliunits_to_currency(milliunits: int, decimal_digits: int = 2) -> Decimal:
    """Convert YNAB milliunits to currency amount using Decimal for precision

    YNAB uses milliunits where 1000 milliunits = 1 currency unit
    """
    return Decimal(milliunits) / Decimal("1000")


class CurrencyFormat(BaseModel):
    """YNAB currency formatting information for proper display of amounts."""

    iso_code: str = Field(
        ..., description="ISO 4217 currency code (e.g., 'USD', 'EUR')"
    )
    example_format: str = Field(
        ..., description="Example of how currency should be formatted (e.g., '$123.45')"
    )
    currency_symbol: str = Field(..., description="Currency symbol (e.g., '$', '€')")

    @classmethod
    def from_ynab(cls, currency_format: ynab.CurrencyFormat) -> CurrencyFormat:
        """Convert YNAB CurrencyFormat object to our CurrencyFormat model."""
        return cls(
            iso_code=currency_format.iso_code,
            example_format=currency_format.example_format,
            currency_symbol=currency_format.currency_symbol,
        )


class Budget(BaseModel):
    """A YNAB budget with metadata and currency information."""

    id: str = Field(..., description="Unique budget identifier")
    name: str = Field(..., description="User-defined budget name")
    last_modified_on: datetime.datetime | None = Field(
        None, description="Timestamp of last modification (UTC)"
    )
    first_month: datetime.date | None = Field(
        None, description="First month available in this budget"
    )
    last_month: datetime.date | None = Field(
        None, description="Last month available in this budget"
    )
    currency_format: CurrencyFormat | None = Field(
        None, description="Currency formatting rules for this budget"
    )

    @classmethod
    def from_ynab(cls, budget: ynab.BudgetSummary) -> Budget:
        """Convert YNAB BudgetSummary object to our Budget model."""
        currency_format = None
        if budget.currency_format:
            currency_format = CurrencyFormat.from_ynab(budget.currency_format)

        return cls(
            id=budget.id,
            name=budget.name,
            last_modified_on=budget.last_modified_on,
            first_month=budget.first_month,
            last_month=budget.last_month,
            currency_format=currency_format,
        )


class PaginationInfo(BaseModel):
    """Pagination metadata for listing endpoints."""

    total_count: int = Field(..., description="Total number of items available")
    limit: int = Field(..., description="Maximum items requested per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(
        ..., description="Whether more items are available beyond this page"
    )
    next_offset: int | None = Field(
        None, description="Offset to use for next page (null if no more pages)"
    )
    returned_count: int = Field(
        ..., description="Actual number of items returned in this page"
    )


class Account(BaseModel):
    """A YNAB account with balance information.

    Note: All balance amounts are provided in currency units using Decimal for
    precision.
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
    note: str | None = Field(None, description="User-defined account notes")
    balance: Decimal | None = Field(
        None, description="Current account balance in currency units"
    )
    cleared_balance: Decimal | None = Field(
        None, description="Balance of cleared transactions in currency units"
    )

    @classmethod
    def from_ynab(cls, account: ynab.Account) -> Account:
        """Convert YNAB Account object to our Account model."""
        return cls(
            id=account.id,
            name=account.name,
            type=account.type,
            on_budget=account.on_budget,
            closed=account.closed,
            note=account.note,
            balance=milliunits_to_currency(account.balance)
            if account.balance is not None
            else None,
            cleared_balance=milliunits_to_currency(account.cleared_balance)
            if account.cleared_balance is not None
            else None,
        )


class Category(BaseModel):
    """A YNAB category with budget and goal information.

    Categories can have different goal types that affect how YNAB handles monthly
    budgeting:
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
    category_group_name: str | None = Field(
        None, description="Name of the category group (included in list_categories)"
    )
    note: str | None = Field(None, description="User-defined category notes")
    budgeted: Decimal | None = Field(
        None, description="Amount budgeted for this category in currency units"
    )
    activity: Decimal | None = Field(
        None,
        description="Total spending activity (negative = spending, positive = income)",
    )
    balance: Decimal | None = Field(
        None, description="Available balance (budgeted + activity)"
    )
    goal_type: str | None = Field(
        None, description="Type of goal set for this category (NEED, TB, TBD, MF)"
    )
    goal_target: Decimal | None = Field(
        None, description="Target amount for the goal in currency units"
    )
    goal_percentage_complete: int | None = Field(
        None, description="Percentage of goal completed (0-100)"
    )
    goal_under_funded: Decimal | None = Field(
        None, description="Amount still needed to meet goal in currency units"
    )

    @classmethod
    def from_ynab(
        cls, category: ynab.Category, category_group_name: str | None = None
    ) -> Category:
        """Convert YNAB Category object to our Category model.

        Args:
            category: The YNAB category object
            category_group_name: Optional category group name to include
        """
        return cls(
            id=category.id,
            name=category.name,
            category_group_id=category.category_group_id,
            category_group_name=category_group_name,
            note=category.note,
            budgeted=milliunits_to_currency(category.budgeted)
            if category.budgeted is not None
            else None,
            activity=milliunits_to_currency(category.activity)
            if category.activity is not None
            else None,
            balance=milliunits_to_currency(category.balance)
            if category.balance is not None
            else None,
            goal_type=category.goal_type,
            goal_target=milliunits_to_currency(category.goal_target)
            if category.goal_target is not None
            else None,
            goal_percentage_complete=category.goal_percentage_complete,
            goal_under_funded=milliunits_to_currency(category.goal_under_funded)
            if category.goal_under_funded is not None
            else None,
        )


class CategoryGroup(BaseModel):
    """A YNAB category group with summary totals.

    Category groups organize related categories together (e.g., 'Monthly Bills',
    'Everyday Expenses').
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
    total_budgeted: Decimal | None = Field(
        None, description="Sum of budgeted amounts for all categories in this group"
    )
    total_activity: Decimal | None = Field(
        None, description="Sum of activity for all categories in this group"
    )
    total_balance: Decimal | None = Field(
        None, description="Sum of balances for all categories in this group"
    )

    @classmethod
    def from_ynab(
        cls, category_group: ynab.CategoryGroupWithCategories
    ) -> CategoryGroup:
        """Convert YNAB CategoryGroup object to our CategoryGroup model.

        Calculates aggregated totals from active (non-deleted, non-hidden) categories.
        """
        # Calculate totals for the group (exclude deleted and hidden categories)
        active_categories = [
            cat
            for cat in category_group.categories
            if not cat.deleted and not cat.hidden
        ]

        total_budgeted = sum(cat.budgeted or 0 for cat in active_categories)
        total_activity = sum(cat.activity or 0 for cat in active_categories)
        total_balance = sum(cat.balance or 0 for cat in active_categories)

        return cls(
            id=category_group.id,
            name=category_group.name,
            hidden=category_group.hidden,
            category_count=len(active_categories),
            total_budgeted=milliunits_to_currency(total_budgeted),
            total_activity=milliunits_to_currency(total_activity),
            total_balance=milliunits_to_currency(total_balance),
        )


class BudgetMonth(BaseModel):
    """Monthly budget summary with category details.

    Provides complete monthly budget information including income, total budgeted
    amounts,
    spending activity, and detailed category breakdowns.
    """

    month: datetime.date | None = Field(None, description="Budget month date")
    note: str | None = Field(
        None, description="User-defined notes for this budget month"
    )
    income: Decimal | None = Field(
        None, description="Total income for the month in currency units"
    )
    budgeted: Decimal | None = Field(
        None, description="Total amount budgeted across all categories"
    )
    activity: Decimal | None = Field(
        None, description="Total spending activity for the month"
    )
    to_be_budgeted: Decimal | None = Field(
        None, description="Amount remaining to be budgeted (can be negative)"
    )
    age_of_money: int | None = Field(
        None,
        description="Age of money in days (how long money sits before being spent)",
    )
    categories: list[Category] = Field(
        ..., description="List of categories with their monthly budget data"
    )
    pagination: PaginationInfo | None = Field(
        None, description="Pagination information for category list"
    )


# Response models for MCP tools
class BudgetsResponse(BaseModel):
    """Response model for list_budgets tool."""

    budgets: list[Budget] = Field(..., description="List of available YNAB budgets")


class AccountsResponse(BaseModel):
    """Response model for list_accounts tool."""

    accounts: list[Account] = Field(..., description="List of accounts in the budget")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class CategoriesResponse(BaseModel):
    """Response model for list_categories tool (structure only, no budget amounts)."""

    categories: list[Category] = Field(
        ..., description="List of category structures (no budget amounts)"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")


class CategoryGroupsResponse(BaseModel):
    """Response model for list_category_groups tool."""

    category_groups: list[CategoryGroup] = Field(
        ..., description="List of category groups with totals"
    )


class BaseTransaction(BaseModel):
    """Base fields shared between Transaction and ScheduledTransaction models."""

    id: str = Field(..., description="Unique identifier")
    amount: Decimal | None = Field(
        None,
        description="Amount in currency units (negative = outflow, positive = inflow)",
    )
    memo: str | None = Field(None, description="User-entered memo/notes")
    flag_color: str | None = Field(
        None,
        description="Flag color: 'red', 'orange', 'yellow', 'green', 'blue', 'purple', "
        "or null",
    )
    account_id: str = Field(..., description="Account ID where transaction occurs")
    account_name: str | None = Field(
        None, description="Account name (included when listing)"
    )
    payee_id: str | None = Field(None, description="Payee ID (who transaction is with)")
    payee_name: str | None = Field(
        None, description="Payee name (included when listing)"
    )
    category_id: str | None = Field(
        None, description="Category ID (null for transfers or uncategorized)"
    )
    category_name: str | None = Field(
        None, description="Category name (included when listing)"
    )
    transfer_account_id: str | None = Field(
        None, description="If a transfer, the account ID of the other side"
    )


class Subtransaction(BaseModel):
    """A subtransaction within a split transaction.

    Subtransactions allow a single transaction to be split across multiple categories.
    The parent transaction's amount must equal the sum of all subtransaction amounts.
    """

    id: str = Field(..., description="Unique subtransaction identifier")
    amount: Decimal | None = Field(
        None, description="Subtransaction amount in currency units"
    )
    memo: str | None = Field(None, description="Subtransaction-specific memo")
    payee_id: str | None = Field(
        None, description="Payee ID (if different from parent)"
    )
    payee_name: str | None = Field(None, description="Payee name")
    category_id: str | None = Field(None, description="Category ID for this portion")
    category_name: str | None = Field(None, description="Category name")
    transfer_account_id: str | None = Field(
        None, description="If a transfer, the account ID"
    )


class ScheduledSubtransaction(BaseModel):
    """A scheduled subtransaction within a split scheduled transaction.

    Similar to Subtransaction but for scheduled transactions.
    """

    id: str = Field(..., description="Unique scheduled subtransaction identifier")
    amount: Decimal | None = Field(
        None, description="Scheduled subtransaction amount in currency units"
    )
    memo: str | None = Field(None, description="Scheduled subtransaction-specific memo")
    payee_id: str | None = Field(
        None, description="Payee ID (if different from parent)"
    )
    payee_name: str | None = Field(None, description="Payee name")
    category_id: str | None = Field(None, description="Category ID for this portion")
    category_name: str | None = Field(None, description="Category name")
    transfer_account_id: str | None = Field(
        None, description="If a transfer, the account ID"
    )


class Transaction(BaseTransaction):
    """A YNAB transaction with full details.

    Transactions represent money moving in or out of accounts. Amounts are negative
    for outflows (spending) and positive for inflows (income/deposits).

    Flag colors can be: 'red', 'orange', 'yellow', 'green', 'blue', 'purple', or null.
    Cleared status can be: 'cleared', 'uncleared', or 'reconciled'.
    """

    date: datetime.date = Field(..., description="Transaction date")
    cleared: str = Field(
        ..., description="Cleared status: 'cleared', 'uncleared', or 'reconciled'"
    )
    approved: bool = Field(
        ...,
        description="Whether transaction is approved (false if imported and "
        "awaiting approval)",
    )

    # Subtransactions for split transactions
    subtransactions: list[Subtransaction] | None = Field(
        None, description="Subtransactions for split transactions"
    )

    @classmethod
    def from_ynab(
        cls, txn: ynab.TransactionDetail | ynab.HybridTransaction
    ) -> Transaction:
        """Convert YNAB transaction object to our Transaction model.

        Handles both TransactionDetail and HybridTransaction types that come from
        different endpoints.
        """
        # Convert amount from milliunits
        amount = milliunits_to_currency(txn.amount)

        # Handle subtransactions if present and available
        subtransactions = None
        if hasattr(txn, "subtransactions") and txn.subtransactions:
            subtransactions = []
            for sub in txn.subtransactions:
                if not sub.deleted:
                    subtransactions.append(
                        Subtransaction(
                            id=sub.id,
                            amount=milliunits_to_currency(sub.amount),
                            memo=sub.memo,
                            payee_id=sub.payee_id,
                            payee_name=sub.payee_name,
                            category_id=sub.category_id,
                            category_name=sub.category_name,
                            transfer_account_id=sub.transfer_account_id,
                        )
                    )

        return cls(
            id=txn.id,
            date=txn.var_date,
            amount=amount,
            memo=txn.memo,
            cleared=txn.cleared,
            approved=txn.approved,
            flag_color=txn.flag_color,
            account_id=txn.account_id,
            account_name=getattr(txn, "account_name", None),
            payee_id=txn.payee_id,
            payee_name=getattr(txn, "payee_name", None),
            category_id=txn.category_id,
            category_name=getattr(txn, "category_name", None),
            transfer_account_id=txn.transfer_account_id,
            subtransactions=subtransactions,
        )


class ScheduledTransaction(BaseTransaction):
    """A YNAB scheduled transaction with frequency and timing details.

    Scheduled transactions represent recurring transactions that YNAB will create
    automatically based on the specified frequency and timing.

    Frequency can be: 'never', 'daily', 'weekly', 'everyOtherWeek', 'twiceAMonth',
    'every4Weeks', 'monthly', 'everyOtherMonth', 'every3Months', 'every4Months',
    'twiceAYear', 'yearly', 'everyOtherYear'
    """

    date_first: datetime.date = Field(
        ..., description="Date of the first occurrence of this scheduled transaction"
    )
    date_next: datetime.date = Field(
        ..., description="Date of the next occurrence of this scheduled transaction"
    )
    frequency: str = Field(
        ...,
        description="Frequency of recurrence (never, daily, weekly, monthly, etc.)",
    )
    flag_name: str | None = Field(
        None, description="Human-readable flag name instead of just color"
    )

    # Subtransactions for split scheduled transactions
    subtransactions: list[ScheduledSubtransaction] | None = Field(
        None, description="Scheduled subtransactions for split scheduled transactions"
    )

    @classmethod
    def from_ynab(cls, st: ynab.ScheduledTransactionDetail) -> ScheduledTransaction:
        """Convert YNAB scheduled transaction object to our ScheduledTransaction model.

        Handles ScheduledTransactionDetail objects from the scheduled transactions API.
        """
        # Convert amount from milliunits
        amount = milliunits_to_currency(st.amount)

        # Handle scheduled subtransactions if present and available
        subtransactions = None
        if hasattr(st, "subtransactions") and st.subtransactions:
            subtransactions = []
            for sub in st.subtransactions:
                if not sub.deleted:
                    subtransactions.append(
                        ScheduledSubtransaction(
                            id=sub.id,
                            amount=milliunits_to_currency(sub.amount),
                            memo=sub.memo,
                            payee_id=sub.payee_id,
                            payee_name=sub.payee_name,
                            category_id=sub.category_id,
                            category_name=sub.category_name,
                            transfer_account_id=sub.transfer_account_id,
                        )
                    )

        return cls(
            id=st.id,
            date_first=st.date_first,
            date_next=st.date_next,
            frequency=st.frequency,
            amount=amount,
            memo=st.memo,
            flag_color=st.flag_color,
            flag_name=getattr(st, "flag_name", None),
            account_id=st.account_id,
            account_name=getattr(st, "account_name", None),
            payee_id=st.payee_id,
            payee_name=getattr(st, "payee_name", None),
            category_id=st.category_id,
            category_name=getattr(st, "category_name", None),
            transfer_account_id=st.transfer_account_id,
            subtransactions=subtransactions,
        )


class TransactionsResponse(BaseModel):
    """Response model for list_transactions tool."""

    transactions: list[Transaction] = Field(
        ..., description="List of transactions matching filters"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")


class Payee(BaseModel):
    """A YNAB payee (person, company, or entity that receives payments).

    Payees can be manually created or automatically created when transactions are
    imported.
    Transfer payees are special system-generated payees for account transfers.
    """

    id: str = Field(..., description="Unique payee identifier")
    name: str = Field(..., description="Payee name")
    transfer_account_id: str | None = Field(
        None, description="If this is a transfer payee, the associated account ID"
    )

    @classmethod
    def from_ynab(cls, payee: ynab.Payee) -> Payee:
        """Convert YNAB Payee object to our Payee model."""
        return cls(
            id=payee.id,
            name=payee.name,
            transfer_account_id=payee.transfer_account_id,
        )


class PayeesResponse(BaseModel):
    """Response model for list_payees tool."""

    payees: list[Payee] = Field(..., description="List of payees in the budget")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class ScheduledTransactionsResponse(BaseModel):
    """Response model for list_scheduled_transactions tool."""

    scheduled_transactions: list[ScheduledTransaction] = Field(
        ..., description="List of scheduled transactions matching filters"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")
