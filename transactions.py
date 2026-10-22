"""
Reading transactions: what was spent and earned, where, and on what.

YNAB returns two shapes of transaction.  The plan-wide list returns whole
transactions, with a split's parts nested inside it.  The lists by category
and by payee return "hybrid" rows instead, where each part of a split is its
own row that points to its parent.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from decimal import Decimal
from typing import Literal
from uuid import UUID

import ynab
from fastmcp.dependencies import Shared
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from currency import currency_to_milliunits, milliunits_to_currency
from effects import READ, READS
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository

TransactionStatus = Literal["unapproved", "uncategorized"]


def format_flag(flag_color: str | None, flag_name: str | None) -> str | None:
    """Format flag as 'Name (Color)' or just color if no name."""
    if not flag_color:
        return None
    if flag_name:
        return f"{flag_name} ({flag_color.title()})"
    return flag_color.title()


class Subtransaction(BaseModel):
    """One part of a split transaction."""

    id: str = Field(..., description="Unique subtransaction identifier")
    amount: Decimal = Field(..., description="Amount in currency units")
    memo: str | None = Field(None, description="Memo")
    payee_id: UUID | None = Field(None, description="Payee ID")
    payee_name: str | None = Field(None, description="Payee name")
    category_id: UUID | None = Field(None, description="Category ID")
    category_name: str | None = Field(None, description="Category name")


class Transaction(BaseModel):
    """A YNAB transaction with full details."""

    id: str = Field(..., description="Unique transaction identifier")
    date: datetime.date = Field(..., description="Transaction date")
    amount: Decimal = Field(
        ...,
        description="Amount in currency units (negative = spending, positive = income)",
    )
    memo: str | None = Field(None, description="User-entered memo")
    cleared: str = Field(
        ..., description="Cleared status: 'cleared', 'uncleared', or 'reconciled'"
    )
    approved: bool = Field(..., description="Whether the transaction is approved")
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
    import_payee_name_original: str | None = Field(
        None,
        description="For an imported transaction, the payee exactly as the bank "
        "wrote it.  Useful for working out the real payee and category.",
    )
    parent_transaction_id: str | None = Field(
        None, description="Parent transaction ID if this is a part of a split"
    )
    subtransactions: list[Subtransaction] | None = Field(
        None, description="The parts of a split transaction"
    )

    @classmethod
    def from_ynab(
        cls,
        txn: ynab.TransactionDetail | ynab.HybridTransaction,
        repository: YNABRepository | None = None,
    ) -> Transaction:
        """Convert a YNAB transaction.

        A part of a split has no payee of its own when it shares its parent's,
        so the repository, when given, looks up the parent to fill it in.
        """
        payee_id = txn.payee_id
        payee_name = txn.payee_name
        parent_transaction_id = None
        subtransactions = None

        if isinstance(txn, ynab.HybridTransaction):
            parent_transaction_id = txn.parent_transaction_id
            if (
                txn.type == "subtransaction"
                and not payee_id
                and not payee_name
                and parent_transaction_id
                and repository
            ):
                parent = fetch_transaction(repository, parent_transaction_id)
                payee_id = parent.payee_id
                payee_name = parent.payee_name
        elif txn.subtransactions:
            subtransactions = [
                Subtransaction(
                    id=sub.id,
                    amount=milliunits_to_currency(sub.amount),
                    memo=sub.memo,
                    payee_id=sub.payee_id or payee_id,
                    payee_name=sub.payee_name or payee_name,
                    category_id=sub.category_id,
                    category_name=sub.category_name,
                )
                for sub in txn.subtransactions
                if not sub.deleted
            ]

        return cls(
            id=txn.id,
            date=txn.var_date,
            amount=milliunits_to_currency(txn.amount),
            memo=txn.memo,
            cleared=txn.cleared,
            approved=txn.approved,
            flag=format_flag(txn.flag_color, txn.flag_name),
            account_id=txn.account_id,
            account_name=txn.account_name,
            payee_id=payee_id,
            payee_name=payee_name,
            category_id=txn.category_id,
            category_name=txn.category_name,
            transfer_account_id=txn.transfer_account_id,
            import_payee_name_original=txn.import_payee_name_original,
            parent_transaction_id=parent_transaction_id,
            subtransactions=subtransactions,
        )


class TransactionsResponse(BaseModel):
    """Response for list_transactions tool."""

    transactions: list[Transaction] = Field(..., description="List of transactions")
    pagination: PaginationInfo = Field(..., description="Pagination information")


def fetch_transaction(
    repository: YNABRepository, transaction_id: str
) -> ynab.TransactionDetail:
    """Fetch one transaction from YNAB."""
    with repository.api() as api_client:
        response = ynab.TransactionsApi(api_client).get_transaction_by_id(
            repository.plan_id, transaction_id
        )
    return response.data.transaction


def fetch_transactions(
    repository: YNABRepository,
    *,
    account_id: UUID | None,
    category_id: UUID | None,
    payee_id: UUID | None,
    since_date: datetime.date | None,
    until_date: datetime.date | None,
    status: TransactionStatus | None,
) -> list[ynab.TransactionDetail | ynab.HybridTransaction]:
    """Fetch transactions, letting YNAB do as much of the filtering as it can.

    YNAB filters by one of account, category, or payee per request.  Account
    and category are applied here too, so any combination of them works.
    Payee is left to the caller, because a part of a split can share its
    parent's payee without carrying it, and only the converted transaction
    knows its payee for certain.

    The lists by category and by payee come first, because they return each
    part of a split as its own row, with the part's category and account.  The
    list by account returns whole splits.  A split's parent has no category, so
    filtering those rows by category would drop every part.
    """
    if not any((account_id, category_id, payee_id, since_date, until_date, status)):
        return list(repository.get_transactions())

    rows: list[ynab.TransactionDetail | ynab.HybridTransaction]
    with repository.api() as api_client:
        api = ynab.TransactionsApi(api_client)
        if category_id:
            rows = list(
                api.get_transactions_by_category(
                    repository.plan_id,
                    str(category_id),
                    since_date=since_date,
                    until_date=until_date,
                    type=status,
                ).data.transactions
            )
        elif payee_id:
            rows = list(
                api.get_transactions_by_payee(
                    repository.plan_id,
                    str(payee_id),
                    since_date=since_date,
                    until_date=until_date,
                    type=status,
                ).data.transactions
            )
        elif account_id:
            rows = list(
                api.get_transactions_by_account(
                    repository.plan_id,
                    str(account_id),
                    since_date=since_date,
                    until_date=until_date,
                    type=status,
                ).data.transactions
            )
        else:
            rows = list(
                api.get_transactions(
                    repository.plan_id,
                    since_date=since_date,
                    until_date=until_date,
                    type=status,
                ).data.transactions
            )

    return [
        row
        for row in rows
        if (account_id is None or row.account_id == account_id)
        and (category_id is None or row.category_id == category_id)
    ]


@tool(title="List transactions", tags={"transactions", READ}, annotations=READS)
def list_transactions(
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    payee_id: UUID | None = None,
    since_date: datetime.date | None = None,
    until_date: datetime.date | None = None,
    status: TransactionStatus | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    text_search: str | None = None,
    limit: int = 25,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> TransactionsResponse:
    """List transactions, newest first, with filters that can be combined.

    Example queries this tool can answer:
    - "Show me all transactions over $50 in Dining Out this year"
      → category_id=<Dining Out>, max_amount=-50, since_date=2024-01-01
    - "What do I still need to review?" → status="unapproved"
    - "What hasn't been categorized?" → status="uncategorized"
    - "How much did we spend at Amazon in March?"
      → payee_id=<Amazon>, since_date=2024-03-01, until_date=2024-03-31
    - "Find the soccer registration fee" → text_search="soccer"

    Filtering by category or payee returns each part of a split transaction as
    its own row, with parent_transaction_id set.

    Args:
        account_id: Only transactions in this account (optional)
        category_id: Only transactions in this category (optional)
        payee_id: Only transactions with this payee (optional)
        since_date: Only transactions on or after this date (optional)
        until_date: Only transactions on or before this date (optional)
        status: "unapproved" for transactions waiting for the user's review, or
            "uncategorized" for transactions with no category (optional)
        min_amount: Only transactions with amount >= this, in currency units.
            Spending is negative, so -50 means "spent at most 50"
            (optional)
        max_amount: Only transactions with amount <= this, in currency units.
            Spending is negative, so -50 means "spent at least 50"
            (optional)
        text_search: Only transactions whose payee name, memo, or original bank
            payee contains this text, ignoring case (optional)
        limit: Maximum number of transactions to return per page (default: 25)
        offset: Number of transactions to skip for pagination (default: 0)

    Returns:
        TransactionsResponse with filtered transactions and pagination info
    """
    rows = fetch_transactions(
        repository,
        account_id=account_id,
        category_id=category_id,
        payee_id=payee_id,
        since_date=since_date,
        until_date=until_date,
        status=status,
    )
    minimum = None if min_amount is None else currency_to_milliunits(min_amount)
    maximum = None if max_amount is None else currency_to_milliunits(max_amount)
    search = text_search.lower() if text_search else None

    converted = [
        Transaction.from_ynab(row, repository)
        for row in rows
        if not row.deleted
        and (minimum is None or row.amount >= minimum)
        and (maximum is None or row.amount <= maximum)
    ]
    transactions = [
        transaction
        for transaction in converted
        if (payee_id is None or transaction.payee_id == payee_id)
        and (search is None or search in searchable_text(transaction))
    ]
    transactions.sort(key=lambda transaction: transaction.date, reverse=True)
    page, pagination = paginate(transactions, limit, offset)
    return TransactionsResponse(transactions=page, pagination=pagination)


def searchable_text(transaction: Transaction) -> str:
    """The text of a transaction that text_search looks through."""
    parts = (
        transaction.payee_name,
        transaction.memo,
        transaction.import_payee_name_original,
    )
    return " ".join(part for part in parts if part).lower()


@tool(title="Get transaction", tags={"transactions", READ}, annotations=READS)
def get_transaction(
    transaction_id: str,
    repository: YNABRepository = Shared(plan_repository),
) -> Transaction:
    """Get one transaction, including the parts of a split.

    Args:
        transaction_id: Transaction to get (required)

    Returns:
        The transaction
    """
    return Transaction.from_ynab(fetch_transaction(repository, transaction_id))


TOOLS: list[Callable[..., object]] = [list_transactions, get_transaction]
