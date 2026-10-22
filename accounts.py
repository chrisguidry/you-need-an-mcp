"""
Accounts: where the plan's money is, and what is owed.

Each account knows the payee that transfers into it use, which is how a
transaction between two accounts is entered.
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
from effects import ADDS, READ, READS, WRITE
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository

NewAccountType = Literal[
    "checking", "savings", "cash", "creditCard", "otherAsset", "otherLiability"
]


def rates_by_date(
    values: dict[str, int] | None, scale: Decimal = Decimal(1)
) -> dict[datetime.date, Decimal] | None:
    """Convert one of YNAB's date-keyed milliunit maps on a debt account."""
    if not values:
        return None
    return {
        datetime.date.fromisoformat(day): milliunits_to_currency(amount) / scale
        for day, amount in values.items()
    }


class Account(BaseModel):
    """A YNAB account with balance information.

    All amounts are in currency units with Decimal precision.
    """

    id: UUID = Field(..., description="Unique account identifier")
    name: str = Field(..., description="User-defined account name")
    type: str = Field(
        ...,
        description="Account type. Common values: 'checking', 'savings', 'creditCard', "
        "'cash', 'lineOfCredit', 'otherAsset', 'otherLiability', 'mortgage', "
        "'autoLoan', 'studentLoan', 'personalLoan', 'medicalDebt', 'otherDebt'",
    )
    on_budget: bool = Field(
        ..., description="Whether this account's money is part of the plan"
    )
    closed: bool = Field(..., description="Whether this account has been closed")
    note: str | None = Field(None, description="User-defined account notes")
    balance: Decimal = Field(..., description="Current balance in currency units")
    cleared_balance: Decimal = Field(
        ..., description="Balance of cleared transactions in currency units"
    )
    uncleared_balance: Decimal = Field(
        ..., description="Balance of uncleared transactions in currency units"
    )
    transfer_payee_id: UUID = Field(
        ...,
        description="Payee to use on a transaction that transfers into this account",
    )
    direct_import_linked: bool | None = Field(
        None, description="Whether the account imports from a bank connection"
    )
    direct_import_in_error: bool | None = Field(
        None, description="Whether the bank connection needs the user's attention"
    )
    last_reconciled_at: datetime.datetime | None = Field(
        None, description="When the account was last reconciled"
    )
    debt_interest_rates: dict[datetime.date, Decimal] | None = Field(
        None,
        description="Interest rates by date for debt accounts. Keys are dates, "
        "values are interest rates as decimals (e.g., 0.03375 for 3.375%)",
    )
    debt_minimum_payments: dict[datetime.date, Decimal] | None = Field(
        None,
        description="Minimum payment amounts by date for debt accounts. "
        "Keys are dates, values are payment amounts in currency units",
    )
    debt_escrow_amounts: dict[datetime.date, Decimal] | None = Field(
        None,
        description="Escrow amounts by date for mortgage accounts. Keys are dates, "
        "values are escrow amounts in currency units",
    )

    @classmethod
    def from_ynab(cls, account: ynab.Account) -> Account:
        """Convert a YNAB account."""
        return cls(
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
            last_reconciled_at=account.last_reconciled_at,
            # YNAB stores a rate of 3.375% as 3375 milliunits.
            debt_interest_rates=rates_by_date(
                account.debt_interest_rates, Decimal(100)
            ),
            debt_minimum_payments=rates_by_date(account.debt_minimum_payments),
            debt_escrow_amounts=rates_by_date(account.debt_escrow_amounts),
        )


class AccountsResponse(BaseModel):
    """Response for list_accounts tool."""

    accounts: list[Account] = Field(..., description="List of accounts")
    pagination: PaginationInfo = Field(..., description="Pagination information")


@tool(title="List accounts", tags={"accounts", READ}, annotations=READS)
def list_accounts(
    include_closed: bool = False,
    limit: int = 100,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> AccountsResponse:
    """List the plan's accounts with their balances.

    Each account includes its transfer_payee_id: use it as the payee of a
    transaction to transfer money into that account.

    Args:
        include_closed: Whether to include closed accounts (default: false)
        limit: Maximum number of accounts to return per page (default: 100)
        offset: Number of accounts to skip for pagination (default: 0)

    Returns:
        AccountsResponse with accounts list and pagination information
    """
    accounts = [
        Account.from_ynab(account)
        for account in repository.get_accounts()
        if not account.deleted and (include_closed or not account.closed)
    ]
    page, pagination = paginate(accounts, limit, offset)
    return AccountsResponse(accounts=page, pagination=pagination)


@tool(title="Create account", tags={"accounts", WRITE}, annotations=ADDS)
def create_account(
    name: str,
    type: NewAccountType,
    balance: Decimal,
    repository: YNABRepository = Shared(plan_repository),
) -> Account:
    """Create an account that the user tracks by hand, such as cash or a new
    savings account.  The account is not connected to a bank.

    Args:
        name: Account name (required)
        type: Account type: "checking", "savings", "cash", "creditCard",
            "otherAsset", or "otherLiability" (required)
        balance: Starting balance in currency units.  Use a negative balance for
            money owed on a credit card or liability (required)

    Returns:
        The new account
    """
    with repository.api() as api_client:
        response = ynab.AccountsApi(api_client).create_account(
            repository.plan_id,
            ynab.PostAccountWrapper(
                account=ynab.SaveAccount(
                    name=name,
                    type=ynab.SaveAccountType(type),
                    balance=currency_to_milliunits(balance),
                )
            ),
        )
    repository.mark_stale("accounts", "payees", "transactions", "category_groups")
    return Account.from_ynab(response.data.account)


TOOLS: list[Callable[..., object]] = [list_accounts, create_account]
