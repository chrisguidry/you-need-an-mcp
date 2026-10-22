"""
Entering a scheduled transaction before its date.

This takes two writes: create the transaction, then move the schedule to its
next date, or delete it if it happens only once.  If the second write fails,
the new transaction is deleted again, so the plan never holds the transaction
and its schedule both.  Without that, YNAB would enter the same bill a second
time on its date.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

import ynab
from fastmcp.dependencies import Shared
from fastmcp.exceptions import ToolError
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from currency import currency_to_milliunits
from effects import ADJUSTS, WRITE
from recurrence import UnknownRecurrence, next_occurrence
from repository import YNABRepository, plan_repository
from scheduled_transactions import (
    ScheduledTransaction,
    fetch_scheduled_transaction,
    put_scheduled,
    refuse_split,
)
from transaction_entry import CHANGED_BY_TRANSACTIONS
from transactions import Transaction

logger = logging.getLogger(__name__)


class EnteredScheduledTransaction(BaseModel):
    """A scheduled transaction that was entered, and what became of its schedule."""

    transaction: Transaction = Field(..., description="The transaction entered")
    schedule: ScheduledTransaction | None = Field(
        None,
        description="The schedule, moved to its next date, or null if it happened "
        "only once and is now deleted",
    )


def entered_transaction(
    st: ynab.ScheduledTransactionDetail,
    date: datetime.date,
    amount_milliunits: int,
    memo: str | None,
) -> ynab.NewTransaction:
    """The transaction that a scheduled transaction becomes when entered."""
    return ynab.NewTransaction(
        account_id=st.account_id,
        date=date,
        amount=amount_milliunits,
        payee_id=st.payee_id,
        category_id=st.category_id,
        memo=memo,
        cleared=ynab.TransactionClearedStatus.UNCLEARED,
        approved=True,
        flag_color=st.flag_color or None,
    )


def advance_schedule(
    repository: YNABRepository,
    st: ynab.ScheduledTransactionDetail,
    next_date: datetime.date | None,
) -> ScheduledTransaction | None:
    """Move a schedule to its next date, or delete it if it has none."""
    if next_date is None:
        with repository.api() as api_client:
            ynab.ScheduledTransactionsApi(api_client).delete_scheduled_transaction(
                repository.plan_id, str(st.id)
            )
        return None

    saved = ynab.SaveScheduledTransaction(
        account_id=st.account_id,
        date=next_date,
        amount=st.amount,
        frequency=ynab.ScheduledTransactionFrequency(st.frequency),
        payee_id=st.payee_id,
        category_id=st.category_id,
        memo=st.memo,
        flag_color=st.flag_color or None,
    )
    return ScheduledTransaction.from_ynab(put_scheduled(repository, st.id, saved))


@tool(
    title="Enter scheduled transaction",
    tags={"scheduled_transactions", WRITE},
    annotations=ADJUSTS,
)
def enter_scheduled_transaction(
    scheduled_transaction_id: UUID,
    date: datetime.date | None = None,
    amount: Decimal | None = None,
    memo: str | None = None,
    repository: YNABRepository = Shared(plan_repository),
) -> EnteredScheduledTransaction:
    """Enter a scheduled transaction now, before its date, like YNAB's "Enter
    Now".  Use this when a bill is paid early or a paycheck arrives early.

    This creates the transaction and moves the schedule to the occurrence after
    its next one.  A schedule that happens only once is deleted.  Split
    scheduled transactions, and those that repeat "twiceAMonth", cannot be
    entered this way; enter them in YNAB.  Calling this twice enters two
    occurrences.

    Args:
        scheduled_transaction_id: Scheduled transaction to enter (required)
        date: Date of the transaction, not in the future (default: today)
        amount: Amount in currency units, when it differs from the scheduled
                amount (optional)
        memo: Memo for the transaction (default: the scheduled memo)

    Returns:
        EnteredScheduledTransaction with the new transaction and the schedule
    """
    st = fetch_scheduled_transaction(repository, scheduled_transaction_id)
    refuse_split(st)
    try:
        next_date = next_occurrence(st.frequency, st.date_first, st.date_next)
    except UnknownRecurrence as error:
        raise ToolError(f"{error}.  Enter it in YNAB instead.") from error

    new = entered_transaction(
        st,
        date or datetime.date.today(),
        st.amount if amount is None else currency_to_milliunits(amount),
        st.memo if memo is None else memo,
    )
    with repository.api() as api_client:
        transactions_api = ynab.TransactionsApi(api_client)
        created = transactions_api.create_transaction(
            repository.plan_id, ynab.PostTransactionsWrapper(transaction=new)
        ).data.transaction
    if created is None:
        raise ToolError("YNAB did not return the entered transaction")
    repository.mark_stale(*CHANGED_BY_TRANSACTIONS)

    try:
        schedule = advance_schedule(repository, st, next_date)
    except Exception:
        logger.warning("Removing an entered transaction whose schedule did not move")
        with repository.api() as api_client:
            ynab.TransactionsApi(api_client).delete_transaction(
                repository.plan_id, created.id
            )
        raise

    return EnteredScheduledTransaction(
        transaction=Transaction.from_ynab(created), schedule=schedule
    )


TOOLS: list[Callable[..., object]] = [enter_scheduled_transaction]
