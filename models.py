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
    """Convert YNAB milliunits to currency amount.

    YNAB uses milliunits where 1000 milliunits = 1 currency unit.
    """
    return Decimal(milliunits) / Decimal("1000")


class PaginationInfo(BaseModel):
    """Pagination metadata for listing endpoints."""

    total_count: int = Field(..., description="Total number of items available")
    limit: int = Field(..., description="Maximum items per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(..., description="Whether more items are available")


class Account(BaseModel):
    """A YNAB account with balance information.

    All amounts are in currency units with Decimal precision.
    """

    id: str = Field(..., description="Unique account identifier")
    name: str = Field(..., description="User-defined account name")
    type: str = Field(
        ...,
        description="Account type. Common values: 'checking', 'savings', 'creditCard', "
        "'cash', 'lineOfCredit', 'otherAsset', 'otherLiability'",
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
    """A YNAB category with budget and goal information."""

    id: str = Field(..., description="Unique category identifier")
    name: str = Field(..., description="Category name")
    category_group_id: str = Field(..., description="Category group ID")
    category_group_name: str | None = Field(None, description="Category group name")
    note: str | None = Field(None, description="Category notes")
    budgeted: Decimal | None = Field(None, description="Amount budgeted")
    activity: Decimal | None = Field(
        None,
        description="Spending activity (negative = spending)",
    )
    balance: Decimal | None = Field(None, description="Available balance")
    goal_type: str | None = Field(
        None,
        description="Goal type: NEED (refill up to X monthly - budget full target), "
        "TB (target balance by date), TBD (target by specific date), MF (funding)",
    )
    goal_target: Decimal | None = Field(None, description="Goal target amount")
    goal_percentage_complete: int | None = Field(
        None, description="Goal percentage complete"
    )
    goal_under_funded: Decimal | None = Field(
        None, description="Amount under-funded for goal"
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
    """A YNAB category group with summary totals."""

    id: str = Field(..., description="Unique category group identifier")
    name: str = Field(..., description="Category group name")
    hidden: bool = Field(..., description="Whether hidden from budget view")
    category_count: int = Field(..., description="Number of categories in group")
    total_budgeted: Decimal | None = Field(None, description="Total budgeted amount")
    total_activity: Decimal | None = Field(None, description="Total activity")
    total_balance: Decimal | None = Field(None, description="Total balance")

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

    Includes income, budgeted amounts, spending activity, and category breakdowns.
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
        ..., description="Categories with monthly budget data"
    )
    pagination: PaginationInfo | None = Field(
        None, description="Pagination information"
    )


# Response models for tools that need pagination
class AccountsResponse(BaseModel):
    """Response for list_accounts tool."""

    accounts: list[Account] = Field(..., description="List of accounts")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class CategoriesResponse(BaseModel):
    """Response for list_categories tool."""

    categories: list[Category] = Field(..., description="List of categories")
    pagination: PaginationInfo = Field(..., description="Pagination information")


def format_flag(flag_color: str | None, flag_name: str | None) -> str | None:
    """Format flag as 'Name (Color)' or just color if no name."""
    if not flag_color:
        return None
    if flag_name:
        return f"{flag_name} ({flag_color.title()})"
    return flag_color.title()


class BaseTransaction(BaseModel):
    """Base fields shared between Transaction and ScheduledTransaction models."""

    id: str = Field(..., description="Unique identifier")
    amount: Decimal | None = Field(
        None,
        description="Amount in currency units (negative = spending, positive = income)",
    )
    memo: str | None = Field(None, description="User-entered memo")
    flag: str | None = Field(
        None,
        description="Flag as 'Name (Color)' format",
    )
    account_id: str = Field(..., description="Account ID")
    account_name: str | None = Field(None, description="Account name")
    payee_id: str | None = Field(None, description="Payee ID")
    payee_name: str | None = Field(None, description="Payee name")
    category_id: str | None = Field(None, description="Category ID")
    category_name: str | None = Field(None, description="Category name")


class Subtransaction(BaseModel):
    """A subtransaction within a split transaction."""

    id: str = Field(..., description="Unique subtransaction identifier")
    amount: Decimal | None = Field(None, description="Amount in currency units")
    memo: str | None = Field(None, description="Memo")
    payee_id: str | None = Field(None, description="Payee ID")
    payee_name: str | None = Field(None, description="Payee name")
    category_id: str | None = Field(None, description="Category ID")
    category_name: str | None = Field(None, description="Category name")


class ScheduledSubtransaction(BaseModel):
    """A scheduled subtransaction within a split scheduled transaction."""

    id: str = Field(..., description="Unique scheduled subtransaction identifier")
    amount: Decimal | None = Field(None, description="Amount in currency units")
    memo: str | None = Field(None, description="Memo")
    payee_id: str | None = Field(None, description="Payee ID")
    payee_name: str | None = Field(None, description="Payee name")
    category_id: str | None = Field(None, description="Category ID")
    category_name: str | None = Field(None, description="Category name")


class Transaction(BaseTransaction):
    """A YNAB transaction with full details."""

    date: datetime.date = Field(..., description="Transaction date")
    cleared: str = Field(..., description="Cleared status")
    approved: bool = Field(
        ...,
        description="Whether transaction is approved",
    )
    subtransactions: list[Subtransaction] | None = Field(
        None, description="Subtransactions for splits"
    )

    @classmethod
    def from_ynab(
        cls, txn: ynab.TransactionDetail | ynab.HybridTransaction
    ) -> Transaction:
        """Convert YNAB transaction object to our Transaction model."""
        # Convert amount from milliunits
        amount = milliunits_to_currency(txn.amount)

        # Get parent transaction payee info
        parent_payee_id = txn.payee_id
        parent_payee_name = getattr(txn, "payee_name", None)

        # Handle subtransactions if present and available
        subtransactions = None
        if hasattr(txn, "subtransactions") and txn.subtransactions:
            subtransactions = []
            for sub in txn.subtransactions:
                if not sub.deleted:
                    # Inherit parent payee info if subtransaction payee is null
                    sub_payee_id = sub.payee_id if sub.payee_id else parent_payee_id
                    sub_payee_name = (
                        sub.payee_name if sub.payee_name else parent_payee_name
                    )

                    subtransactions.append(
                        Subtransaction(
                            id=sub.id,
                            amount=milliunits_to_currency(sub.amount),
                            memo=sub.memo,
                            payee_id=sub_payee_id,
                            payee_name=sub_payee_name,
                            category_id=sub.category_id,
                            category_name=sub.category_name,
                        )
                    )

        return cls(
            id=txn.id,
            date=txn.var_date,
            amount=amount,
            memo=txn.memo,
            cleared=txn.cleared,
            approved=txn.approved,
            flag=format_flag(txn.flag_color, getattr(txn, "flag_name", None)),
            account_id=txn.account_id,
            account_name=getattr(txn, "account_name", None),
            payee_id=parent_payee_id,
            payee_name=parent_payee_name,
            category_id=txn.category_id,
            category_name=getattr(txn, "category_name", None),
            subtransactions=subtransactions,
        )


class ScheduledTransaction(BaseTransaction):
    """A YNAB scheduled transaction with frequency and timing details."""

    date_first: datetime.date = Field(..., description="First occurrence date")
    date_next: datetime.date = Field(..., description="Next occurrence date")
    frequency: str = Field(
        ...,
        description="Recurrence frequency",
    )
    subtransactions: list[ScheduledSubtransaction] | None = Field(
        None, description="Scheduled subtransactions for splits"
    )

    @classmethod
    def from_ynab(cls, st: ynab.ScheduledTransactionDetail) -> ScheduledTransaction:
        """Convert YNAB scheduled transaction to ScheduledTransaction model."""
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
                        )
                    )

        return cls(
            id=st.id,
            date_first=st.date_first,
            date_next=st.date_next,
            frequency=st.frequency,
            amount=amount,
            memo=st.memo,
            flag=format_flag(st.flag_color, getattr(st, "flag_name", None)),
            account_id=st.account_id,
            account_name=getattr(st, "account_name", None),
            payee_id=st.payee_id,
            payee_name=getattr(st, "payee_name", None),
            category_id=st.category_id,
            category_name=getattr(st, "category_name", None),
            subtransactions=subtransactions,
        )


class TransactionsResponse(BaseModel):
    """Response for list_transactions tool."""

    transactions: list[Transaction] = Field(..., description="List of transactions")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class Payee(BaseModel):
    """A YNAB payee (person, company, or entity that receives payments)."""

    id: str = Field(..., description="Unique payee identifier")
    name: str = Field(..., description="Payee name")

    @classmethod
    def from_ynab(cls, payee: ynab.Payee) -> Payee:
        """Convert YNAB Payee object to our Payee model."""
        return cls(
            id=payee.id,
            name=payee.name,
        )


class PayeesResponse(BaseModel):
    """Response for list_payees tool."""

    payees: list[Payee] = Field(..., description="List of payees")
    pagination: PaginationInfo = Field(..., description="Pagination information")


class ScheduledTransactionsResponse(BaseModel):
    """Response for list_scheduled_transactions tool."""

    scheduled_transactions: list[ScheduledTransaction] = Field(
        ..., description="List of scheduled transactions"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")
