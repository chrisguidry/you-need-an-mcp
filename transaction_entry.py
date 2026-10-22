"""
Entering and editing transactions.

The tools take lists, so a stack of receipts, a statement, or a week of review
goes to YNAB in one request.  An edit sends only the fields it names, and YNAB
leaves every other field as it was.
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

from currency import currency_to_milliunits
from effects import ADDS, REMOVES, SETS, WRITE
from repository import YNABRepository, plan_repository
from transactions import Transaction

FlagColor = Literal["red", "orange", "yellow", "green", "blue", "purple"]
ClearedStatus = Literal["cleared", "uncleared", "reconciled"]

# A transaction changes balances, category activity, and maybe the payee list.
CHANGED_BY_TRANSACTIONS = ("transactions", "accounts", "category_groups", "payees")


class SplitPart(BaseModel):
    """One part of a split transaction."""

    amount: Decimal = Field(
        ..., description="Amount in currency units (negative = spending)"
    )
    category_id: UUID | None = Field(None, description="Category for this part")
    payee_id: UUID | None = Field(None, description="Payee, if not the parent's")
    payee_name: str | None = Field(
        None, description="Payee by name, if not the parent's.  Creates it if new"
    )
    memo: str | None = Field(None, description="Memo for this part")


class TransactionEntry(BaseModel):
    """A transaction to create."""

    account_id: UUID = Field(..., description="Account the transaction is in")
    date: datetime.date = Field(..., description="Transaction date, not in the future")
    amount: Decimal = Field(
        ...,
        description="Amount in currency units: negative for spending, positive for "
        "income or refunds",
    )
    payee_id: UUID | None = Field(None, description="Payee, by ID")
    payee_name: str | None = Field(
        None,
        description="Payee by name, when payee_id is not given.  YNAB uses the "
        "payee with this name, or creates it",
    )
    transfer_account_id: UUID | None = Field(
        None,
        description="For a transfer, the other account.  Use instead of a payee",
    )
    category_id: UUID | None = Field(
        None,
        description="Category.  Income goes to 'Inflow: Ready to Assign'.  Leave "
        "empty for a transfer between two accounts in the plan, or for a split",
    )
    memo: str | None = Field(None, description="Memo, at most 500 characters")
    cleared: ClearedStatus = Field("uncleared", description="Cleared status")
    approved: bool = Field(
        True,
        description="Whether the user has approved it.  Entries made at the "
        "user's request are approved",
    )
    flag_color: FlagColor | None = Field(None, description="Flag color")
    splits: list[SplitPart] | None = Field(
        None,
        description="Parts of a split transaction.  Their amounts must add up to "
        "the transaction's amount",
    )


class TransactionChange(BaseModel):
    """Changes to one existing transaction.  Fields left out do not change."""

    id: str = Field(..., description="Transaction to change")
    account_id: UUID | None = Field(None, description="Move it to this account")
    date: datetime.date | None = Field(None, description="New date")
    amount: Decimal | None = Field(
        None,
        description="New amount in currency units.  A split's amount cannot change",
    )
    payee_id: UUID | None = Field(None, description="New payee, by ID")
    payee_name: str | None = Field(
        None, description="New payee by name.  Creates it if new"
    )
    transfer_account_id: UUID | None = Field(
        None, description="Make it a transfer with this account"
    )
    category_id: UUID | None = Field(None, description="New category")
    memo: str | None = Field(None, description="New memo.  An empty memo clears it")
    cleared: ClearedStatus | None = Field(None, description="New cleared status")
    approved: bool | None = Field(None, description="Approve it, or unapprove it")
    flag_color: FlagColor | None = Field(None, description="New flag color")
    clear_flag: bool = Field(False, description="Remove the flag")
    splits: list[SplitPart] | None = Field(
        None,
        description="Split a transaction that is not split yet.  YNAB cannot change "
        "the parts of a transaction that is already split",
    )


def transfer_payee(repository: YNABRepository, account_id: UUID) -> UUID:
    """The payee that moves money into an account."""
    for account in repository.get_accounts():
        if account.id == account_id and not account.deleted:
            return account.transfer_payee_id
    raise ToolError(f"No account {account_id} to transfer to")


def save_splits(splits: list[SplitPart]) -> list[ynab.SaveSubTransaction]:
    """Convert split parts to YNAB's subtransactions."""
    return [
        ynab.SaveSubTransaction(
            amount=currency_to_milliunits(part.amount),
            category_id=part.category_id,
            payee_id=part.payee_id,
            payee_name=part.payee_name,
            memo=part.memo,
        )
        for part in splits
    ]


def new_transaction(
    repository: YNABRepository, entry: TransactionEntry
) -> ynab.NewTransaction:
    """Convert one entry to the transaction YNAB creates."""
    if entry.splits and sum(part.amount for part in entry.splits) != entry.amount:
        raise ToolError(
            f"The splits of the {entry.amount} transaction on {entry.date} add up "
            f"to {sum(part.amount for part in entry.splits)}"
        )
    payee_id = entry.payee_id
    if entry.transfer_account_id:
        payee_id = transfer_payee(repository, entry.transfer_account_id)

    return ynab.NewTransaction(
        account_id=entry.account_id,
        date=entry.date,
        amount=currency_to_milliunits(entry.amount),
        payee_id=payee_id,
        payee_name=entry.payee_name,
        category_id=entry.category_id,
        memo=entry.memo,
        cleared=ynab.TransactionClearedStatus(entry.cleared),
        approved=entry.approved,
        flag_color=ynab.TransactionFlagColor(entry.flag_color)
        if entry.flag_color
        else None,
        subtransactions=save_splits(entry.splits) if entry.splits else None,
    )


@tool(title="Create transactions", tags={"transactions", WRITE}, annotations=ADDS)
def create_transactions(
    transactions: list[TransactionEntry],
    repository: YNABRepository = Shared(plan_repository),
) -> list[Transaction]:
    """Create one or more transactions in one request.

    Use this to enter spending from a receipt, record income, enter a transfer
    between accounts, or add a split transaction.  Calling this twice enters
    the transactions twice.

    Example entries:
    - Spending: account_id=<Checking>, date=2024-03-02, amount=-43.17,
      payee_name="Kroger", category_id=<Groceries>
    - Income: amount=2500, payee_name="Acme Payroll",
      category_id=<Inflow: Ready to Assign>
    - Transfer: account_id=<Checking>, amount=-200,
      transfer_account_id=<Savings>, no category
    - Split: amount=-80, payee_name="Target", no category, splits=[
      {amount: -50, category_id: <Groceries>},
      {amount: -30, category_id: <Household>}]

    Args:
        transactions: The transactions to create (required)

    Returns:
        The created transactions, as YNAB saved them
    """
    if not transactions:
        raise ToolError("Give at least one transaction to create")
    entries = [new_transaction(repository, entry) for entry in transactions]

    with repository.api() as api_client:
        response = ynab.TransactionsApi(api_client).create_transaction(
            repository.plan_id, ynab.PostTransactionsWrapper(transactions=entries)
        )
    repository.mark_stale(*CHANGED_BY_TRANSACTIONS)
    return [Transaction.from_ynab(saved) for saved in response.data.transactions or []]


def saved_change(
    repository: YNABRepository, change: TransactionChange
) -> ynab.SaveTransactionWithIdOrImportId:
    """Convert one change to YNAB's update, with only the fields it names."""
    fields: dict[str, object] = {"id": change.id}
    if change.account_id is not None:
        fields["account_id"] = change.account_id
    if change.date is not None:
        fields["date"] = change.date
    if change.amount is not None:
        fields["amount"] = currency_to_milliunits(change.amount)
    if change.payee_id is not None:
        fields["payee_id"] = change.payee_id
    if change.payee_name is not None:
        fields["payee_name"] = change.payee_name
    if change.transfer_account_id is not None:
        fields["payee_id"] = transfer_payee(repository, change.transfer_account_id)
    if change.category_id is not None:
        fields["category_id"] = change.category_id
    if change.memo is not None:
        fields["memo"] = change.memo
    if change.cleared is not None:
        fields["cleared"] = ynab.TransactionClearedStatus(change.cleared)
    if change.approved is not None:
        fields["approved"] = change.approved
    if change.flag_color is not None:
        fields["flag_color"] = ynab.TransactionFlagColor(change.flag_color)
    if change.clear_flag:
        # YNAB clears a flag only when the field is sent as null, and the SDK
        # sends null only for a field that was set explicitly.
        fields["flag_color"] = None
    if change.splits:
        fields["subtransactions"] = save_splits(change.splits)
    return ynab.SaveTransactionWithIdOrImportId.model_validate(fields)


@tool(title="Update transactions", tags={"transactions", WRITE}, annotations=SETS)
def update_transactions(
    changes: list[TransactionChange],
    repository: YNABRepository = Shared(plan_repository),
) -> list[Transaction]:
    """Change one or more existing transactions in one request.

    Each change names a transaction and only the fields to change; every other
    field stays as it is.  This is the tool for reviewing transactions: approve
    them, categorize them, fix payees, set memos, flag them, or mark them
    cleared.

    Example changes:
    - Approve and categorize: {id: <txn>, approved: true, category_id: <Dining>}
    - Fix the payee: {id: <txn>, payee_name: "Costco"}
    - Clear the memo and the flag: {id: <txn>, memo: "", clear_flag: true}

    Args:
        changes: The changes, one per transaction (required)

    Returns:
        The changed transactions, as YNAB saved them
    """
    if not changes:
        raise ToolError("Give at least one change")
    saved = [saved_change(repository, change) for change in changes]

    with repository.api() as api_client:
        response = ynab.TransactionsApi(api_client).update_transactions(
            repository.plan_id, ynab.PatchTransactionsWrapper(transactions=saved)
        )
    repository.mark_stale(*CHANGED_BY_TRANSACTIONS)
    return [Transaction.from_ynab(txn) for txn in response.data.transactions or []]


@tool(title="Delete transaction", tags={"transactions", WRITE}, annotations=REMOVES)
def delete_transaction(
    transaction_id: str,
    repository: YNABRepository = Shared(plan_repository),
) -> Transaction:
    """Delete a transaction.  Confirm with the user before deleting.

    Args:
        transaction_id: Transaction to delete (required)

    Returns:
        The transaction as it was before it was deleted
    """
    with repository.api() as api_client:
        response = ynab.TransactionsApi(api_client).delete_transaction(
            repository.plan_id, transaction_id
        )
    repository.mark_stale(*CHANGED_BY_TRANSACTIONS)
    return Transaction.from_ynab(response.data.transaction)


class ImportResult(BaseModel):
    """What an import from linked accounts brought in."""

    imported_count: int = Field(..., description="Number of new transactions")
    transaction_ids: list[str] = Field(..., description="IDs of the new transactions")


@tool(title="Import transactions", tags={"transactions", WRITE}, annotations=ADDS)
def import_transactions(
    repository: YNABRepository = Shared(plan_repository),
) -> ImportResult:
    """Ask YNAB to import new transactions from the plan's linked bank accounts
    now, instead of waiting for its next scheduled import.

    Imported transactions arrive unapproved.  Find them with list_transactions
    and status="unapproved".

    Returns:
        ImportResult with the IDs of the imported transactions
    """
    with repository.api() as api_client:
        response = ynab.TransactionsApi(api_client).import_transactions(
            repository.plan_id
        )
    repository.mark_stale(*CHANGED_BY_TRANSACTIONS)
    ids = list(response.data.transaction_ids)
    return ImportResult(imported_count=len(ids), transaction_ids=ids)


TOOLS: list[Callable[..., object]] = [
    create_transactions,
    update_transactions,
    delete_transaction,
    import_transactions,
]
