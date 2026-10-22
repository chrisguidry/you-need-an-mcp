"""
Scheduled transactions: bills, paychecks, and other money YNAB expects.

YNAB enters a scheduled transaction into its account on its date by itself.
Entering one early, before its date, is the same as what YNAB's "Enter Now"
does: create the transaction, then move the schedule to its next date.

YNAB's API cannot create or change a split scheduled transaction.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal
from typing import Literal
from uuid import UUID

import ynab
from fastmcp.dependencies import Shared
from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from currency import currency_to_milliunits, milliunits_to_currency
from effects import ADDS, READ, READS, REMOVES, SETS, WRITE
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository
from transaction_entry import FlagColor, transfer_payee
from transactions import format_flag

Frequency = Literal[
    "never",
    "daily",
    "weekly",
    "everyOtherWeek",
    "twiceAMonth",
    "every4Weeks",
    "monthly",
    "everyOtherMonth",
    "every3Months",
    "every4Months",
    "twiceAYear",
    "yearly",
    "everyOtherYear",
]


class ScheduledSubtransaction(BaseModel):
    """One part of a split scheduled transaction."""

    id: UUID = Field(..., description="Unique scheduled subtransaction identifier")
    amount: Decimal = Field(..., description="Amount in currency units")
    memo: str | None = Field(None, description="Memo")
    payee_id: UUID | None = Field(None, description="Payee ID")
    payee_name: str | None = Field(None, description="Payee name")
    category_id: UUID | None = Field(None, description="Category ID")
    category_name: str | None = Field(None, description="Category name")


class ScheduledTransaction(BaseModel):
    """A YNAB scheduled transaction with its frequency and dates."""

    id: UUID = Field(..., description="Unique scheduled transaction identifier")
    date_first: datetime.date = Field(..., description="First occurrence date")
    date_next: datetime.date = Field(..., description="Next occurrence date")
    frequency: str = Field(..., description="How often it happens")
    amount: Decimal = Field(
        ...,
        description="Amount in currency units (negative = spending, positive = income)",
    )
    memo: str | None = Field(None, description="User-entered memo")
    flag: str | None = Field(None, description="Flag as 'Name (Color)' format")
    account_id: UUID = Field(..., description="Account ID")
    account_name: str | None = Field(None, description="Account name")
    payee_id: UUID | None = Field(None, description="Payee ID")
    payee_name: str | None = Field(None, description="Payee name")
    category_id: UUID | None = Field(None, description="Category ID")
    category_name: str | None = Field(None, description="Category name")
    transfer_account_id: UUID | None = Field(
        None, description="For a transfer, the other account"
    )
    subtransactions: list[ScheduledSubtransaction] | None = Field(
        None, description="The parts of a split scheduled transaction"
    )

    @classmethod
    def from_ynab(cls, st: ynab.ScheduledTransactionDetail) -> ScheduledTransaction:
        """Convert a YNAB scheduled transaction."""
        subtransactions = [
            ScheduledSubtransaction(
                id=sub.id,
                amount=milliunits_to_currency(sub.amount),
                memo=sub.memo,
                payee_id=sub.payee_id,
                payee_name=sub.payee_name,
                category_id=sub.category_id,
                category_name=sub.category_name,
            )
            for sub in st.subtransactions
            if not sub.deleted
        ]
        return cls(
            id=st.id,
            date_first=st.date_first,
            date_next=st.date_next,
            frequency=st.frequency,
            amount=milliunits_to_currency(st.amount),
            memo=st.memo,
            flag=format_flag(st.flag_color, st.flag_name),
            account_id=st.account_id,
            account_name=st.account_name,
            payee_id=st.payee_id,
            payee_name=st.payee_name,
            category_id=st.category_id,
            category_name=st.category_name,
            transfer_account_id=st.transfer_account_id,
            subtransactions=subtransactions or None,
        )


class ScheduledTransactionsResponse(BaseModel):
    """Response for list_scheduled_transactions tool."""

    scheduled_transactions: list[ScheduledTransaction] = Field(
        ..., description="List of scheduled transactions"
    )
    pagination: PaginationInfo = Field(..., description="Pagination information")


def fetch_scheduled_transaction(
    repository: YNABRepository, scheduled_transaction_id: UUID
) -> ynab.ScheduledTransactionDetail:
    """Fetch one scheduled transaction from YNAB."""
    with repository.api() as api_client:
        response = ynab.ScheduledTransactionsApi(
            api_client
        ).get_scheduled_transaction_by_id(
            repository.plan_id, str(scheduled_transaction_id)
        )
    return response.data.scheduled_transaction


@tool(
    title="List scheduled transactions",
    tags={"scheduled_transactions", READ},
    annotations=READS,
)
def list_scheduled_transactions(
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    payee_id: UUID | None = None,
    frequency: Frequency | None = None,
    upcoming_days: int | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    limit: int = 25,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> ScheduledTransactionsResponse:
    """List scheduled transactions, soonest first, with filters that can be
    combined.

    Example queries this tool can answer:
    - "Show me all monthly recurring expenses" (use frequency="monthly")
    - "What bills are due in the next 7 days?" (use upcoming_days=7)
    - "List all Netflix subscriptions" (find the payee first, then use payee_id)
    - "Show scheduled income over $100" (use min_amount=100)

    Args:
        account_id: Only scheduled transactions in this account (optional)
        category_id: Only scheduled transactions in this category (optional)
        payee_id: Only scheduled transactions with this payee (optional)
        frequency: Only scheduled transactions that repeat this often (optional)
        upcoming_days: Only scheduled transactions due within this many days
                       (optional)
        min_amount: Only amounts >= this, in currency units.  Spending is
                    negative (optional)
        max_amount: Only amounts <= this, in currency units.  Spending is
                    negative (optional)
        limit: Maximum number to return per page (default: 25)
        offset: Number to skip for pagination (default: 0)

    Returns:
        ScheduledTransactionsResponse with scheduled transactions and pagination
    """
    with repository.api() as api_client:
        response = ynab.ScheduledTransactionsApi(api_client).get_scheduled_transactions(
            repository.plan_id
        )

    today = datetime.date.today()
    minimum = None if min_amount is None else currency_to_milliunits(min_amount)
    maximum = None if max_amount is None else currency_to_milliunits(max_amount)
    scheduled = [
        ScheduledTransaction.from_ynab(st)
        for st in response.data.scheduled_transactions
        if not st.deleted
        and (account_id is None or st.account_id == account_id)
        and (category_id is None or st.category_id == category_id)
        and (payee_id is None or st.payee_id == payee_id)
        and (frequency is None or st.frequency == frequency)
        and (upcoming_days is None or (st.date_next - today).days <= upcoming_days)
        and (minimum is None or st.amount >= minimum)
        and (maximum is None or st.amount <= maximum)
    ]
    scheduled.sort(key=lambda st: st.date_next)
    page, pagination = paginate(scheduled, limit, offset)
    return ScheduledTransactionsResponse(
        scheduled_transactions=page, pagination=pagination
    )


@tool(
    title="Get scheduled transaction",
    tags={"scheduled_transactions", READ},
    annotations=READS,
)
def get_scheduled_transaction(
    scheduled_transaction_id: UUID,
    repository: YNABRepository = Shared(plan_repository),
) -> ScheduledTransaction:
    """Get one scheduled transaction.

    Args:
        scheduled_transaction_id: Scheduled transaction to get (required)

    Returns:
        The scheduled transaction
    """
    return ScheduledTransaction.from_ynab(
        fetch_scheduled_transaction(repository, scheduled_transaction_id)
    )


def save_scheduled(
    repository: YNABRepository,
    *,
    account_id: UUID,
    date: datetime.date,
    amount_milliunits: int,
    frequency: str,
    payee_id: UUID | None,
    payee_name: str | None,
    transfer_account_id: UUID | None,
    category_id: UUID | None,
    memo: str | None,
    flag_color: str | None,
) -> ynab.SaveScheduledTransaction:
    """Build the scheduled transaction YNAB saves."""
    if transfer_account_id:
        payee_id = transfer_payee(repository, transfer_account_id)
    return ynab.SaveScheduledTransaction(
        account_id=account_id,
        date=date,
        amount=amount_milliunits,
        frequency=ynab.ScheduledTransactionFrequency(frequency),
        payee_id=payee_id,
        payee_name=payee_name,
        category_id=category_id,
        memo=memo,
        flag_color=ynab.TransactionFlagColor(flag_color) if flag_color else None,
    )


@tool(
    title="Create scheduled transaction",
    tags={"scheduled_transactions", WRITE},
    annotations=ADDS,
)
def create_scheduled_transaction(
    account_id: UUID,
    date: datetime.date,
    amount: Decimal,
    frequency: Frequency,
    payee_id: UUID | None = None,
    payee_name: str | None = None,
    transfer_account_id: UUID | None = None,
    category_id: UUID | None = None,
    memo: str | None = None,
    flag_color: FlagColor | None = None,
    repository: YNABRepository = Shared(plan_repository),
) -> ScheduledTransaction:
    """Schedule a transaction: a bill, a paycheck, or a regular transfer.

    Args:
        account_id: Account it happens in (required)
        date: First date it happens: in the future, at most 5 years out (required)
        amount: Amount in currency units: negative for spending, positive for
                income (required)
        frequency: How often it repeats, or "never" for once (required)
        payee_id: Payee, by ID (optional)
        payee_name: Payee by name, when payee_id is not given.  YNAB uses the
                    payee with this name, or creates it (optional)
        transfer_account_id: For a transfer, the other account.  Use instead of
                             a payee (optional)
        category_id: Category.  Credit card payment categories are not allowed
                     (optional)
        memo: Memo, at most 500 characters (optional)
        flag_color: Flag color (optional)

    Returns:
        The new scheduled transaction
    """
    saved = save_scheduled(
        repository,
        account_id=account_id,
        date=date,
        amount_milliunits=currency_to_milliunits(amount),
        frequency=frequency,
        payee_id=payee_id,
        payee_name=payee_name,
        transfer_account_id=transfer_account_id,
        category_id=category_id,
        memo=memo,
        flag_color=flag_color,
    )
    with repository.api() as api_client:
        response = ynab.ScheduledTransactionsApi(
            api_client
        ).create_scheduled_transaction(
            repository.plan_id,
            ynab.PostScheduledTransactionWrapper(scheduled_transaction=saved),
        )
    return ScheduledTransaction.from_ynab(response.data.scheduled_transaction)


def refuse_split(st: ynab.ScheduledTransactionDetail) -> None:
    """Stop before changing a split, which YNAB's API cannot save."""
    if any(not sub.deleted for sub in st.subtransactions):
        raise ToolError(
            "This scheduled transaction is split, and YNAB's API cannot change a "
            "split scheduled transaction.  Change it in YNAB instead."
        )


def put_scheduled(
    repository: YNABRepository,
    scheduled_transaction_id: UUID,
    saved: ynab.SaveScheduledTransaction,
) -> ynab.ScheduledTransactionDetail:
    """Replace a scheduled transaction with a new version of it."""
    with repository.api() as api_client:
        response = ynab.ScheduledTransactionsApi(
            api_client
        ).update_scheduled_transaction(
            repository.plan_id,
            str(scheduled_transaction_id),
            ynab.PutScheduledTransactionWrapper(scheduled_transaction=saved),
        )
    return response.data.scheduled_transaction


@tool(
    title="Update scheduled transaction",
    tags={"scheduled_transactions", WRITE},
    annotations=SETS,
)
def update_scheduled_transaction(
    scheduled_transaction_id: UUID,
    account_id: UUID | None = None,
    date: datetime.date | None = None,
    amount: Decimal | None = None,
    frequency: Frequency | None = None,
    payee_id: UUID | None = None,
    payee_name: str | None = None,
    transfer_account_id: UUID | None = None,
    category_id: UUID | None = None,
    memo: str | None = None,
    flag_color: FlagColor | None = None,
    repository: YNABRepository = Shared(plan_repository),
) -> ScheduledTransaction:
    """Change a scheduled transaction.  Fields left out do not change.

    Use this when a bill's amount changes, it moves to another day or account,
    or it repeats on a new schedule.  Split scheduled transactions cannot be
    changed through YNAB's API.

    Args:
        scheduled_transaction_id: Scheduled transaction to change (required)
        account_id: New account (optional)
        date: New next date: in the future, at most 5 years out (optional)
        amount: New amount in currency units (optional)
        frequency: New frequency (optional)
        payee_id: New payee, by ID (optional)
        payee_name: New payee by name.  Creates it if new (optional)
        transfer_account_id: Make it a transfer with this account (optional)
        category_id: New category (optional)
        memo: New memo.  An empty memo clears it (optional)
        flag_color: New flag color (optional)

    Returns:
        The changed scheduled transaction
    """
    st = fetch_scheduled_transaction(repository, scheduled_transaction_id)
    refuse_split(st)
    new_payee = payee_id or payee_name or transfer_account_id
    saved = save_scheduled(
        repository,
        account_id=account_id or st.account_id,
        date=date or st.date_next,
        amount_milliunits=(
            st.amount if amount is None else currency_to_milliunits(amount)
        ),
        frequency=frequency or st.frequency,
        payee_id=payee_id if new_payee else st.payee_id,
        payee_name=payee_name,
        transfer_account_id=transfer_account_id,
        category_id=category_id or st.category_id,
        memo=st.memo if memo is None else memo,
        flag_color=flag_color or st.flag_color,
    )
    return ScheduledTransaction.from_ynab(
        put_scheduled(repository, scheduled_transaction_id, saved)
    )


@tool(
    title="Delete scheduled transaction",
    tags={"scheduled_transactions", WRITE},
    annotations=REMOVES,
)
def delete_scheduled_transaction(
    scheduled_transaction_id: UUID,
    repository: YNABRepository = Shared(plan_repository),
) -> ScheduledTransaction:
    """Delete a scheduled transaction, so it stops happening.  Transactions it
    already entered stay.  Confirm with the user before deleting.

    Args:
        scheduled_transaction_id: Scheduled transaction to delete (required)

    Returns:
        The scheduled transaction as it was before it was deleted
    """
    with repository.api() as api_client:
        response = ynab.ScheduledTransactionsApi(
            api_client
        ).delete_scheduled_transaction(
            repository.plan_id, str(scheduled_transaction_id)
        )
    return ScheduledTransaction.from_ynab(response.data.scheduled_transaction)


TOOLS: list[Callable[..., object]] = [
    list_scheduled_transactions,
    get_scheduled_transaction,
    create_scheduled_transaction,
    update_scheduled_transaction,
    delete_scheduled_transaction,
]
