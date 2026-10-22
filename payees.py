"""
Payees: the people and businesses money goes to and comes from.

Transfers have payees too.  A transfer payee belongs to an account, and a
transaction with that payee moves money into the account.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import ynab
from fastmcp.dependencies import Shared
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from effects import ADDS, READ, READS, SETS, WRITE
from pagination import PaginationInfo, paginate
from repository import YNABRepository, plan_repository


class Payee(BaseModel):
    """A YNAB payee (person, company, or entity that receives payments)."""

    id: UUID = Field(..., description="Unique payee identifier")
    name: str = Field(..., description="Payee name")
    transfer_account_id: UUID | None = Field(
        None,
        description="For a transfer payee, the account that transfers to it go into",
    )

    @classmethod
    def from_ynab(cls, payee: ynab.Payee) -> Payee:
        """Convert a YNAB payee."""
        return cls(
            id=payee.id,
            name=payee.name,
            transfer_account_id=(
                UUID(payee.transfer_account_id) if payee.transfer_account_id else None
            ),
        )


class PayeesResponse(BaseModel):
    """Response for list_payees and find_payee tools."""

    payees: list[Payee] = Field(..., description="List of payees")
    pagination: PaginationInfo = Field(..., description="Pagination information")


def active_payees(repository: YNABRepository) -> list[Payee]:
    """Every payee that is not deleted, sorted by name."""
    payees = [
        Payee.from_ynab(payee) for payee in repository.get_payees() if not payee.deleted
    ]
    payees.sort(key=lambda payee: payee.name.lower())
    return payees


@tool(title="List payees", tags={"payees", READ}, annotations=READS)
def list_payees(
    limit: int = 50,
    offset: int = 0,
    repository: YNABRepository = Shared(plan_repository),
) -> PayeesResponse:
    """List the plan's payees, sorted by name.

    Payees are the people and businesses money goes to and comes from.  To find
    a particular payee, find_payee is much faster than paging through this list.
    Deleted payees are excluded.

    Args:
        limit: Maximum number of payees to return per page (default: 50)
        offset: Number of payees to skip for pagination (default: 0)

    Returns:
        PayeesResponse with payees list and pagination information
    """
    page, pagination = paginate(active_payees(repository), limit, offset)
    return PayeesResponse(payees=page, pagination=pagination)


@tool(title="Find payee", tags={"payees", READ}, annotations=READS)
def find_payee(
    name_search: str,
    limit: int = 10,
    repository: YNABRepository = Shared(plan_repository),
) -> PayeesResponse:
    """Find payees whose names contain a search term, ignoring case.

    Example queries this tool can answer:
    - "Find Amazon payee ID" (use name_search="amazon")
    - "Show me all Starbucks locations" (use name_search="starbucks")
    - "Find payees with 'grocery' in the name" (use name_search="grocery")

    Args:
        name_search: Text to look for in payee names.  Examples: "amazon",
            "starbucks", "grocery" (required)
        limit: Maximum number of matching payees to return (default: 10)

    Returns:
        PayeesResponse with matching payees and pagination information
    """
    search_term = name_search.lower().strip()
    matches = [
        payee
        for payee in active_payees(repository)
        if search_term in payee.name.lower()
    ]
    page, pagination = paginate(matches, limit, 0)
    return PayeesResponse(payees=page, pagination=pagination)


@tool(title="Create payee", tags={"payees", WRITE}, annotations=ADDS)
def create_payee(
    name: str,
    repository: YNABRepository = Shared(plan_repository),
) -> Payee:
    """Create a payee.

    A new transaction can also create its payee by giving payee_name, so this is
    only needed to set up a payee before any transaction uses it.

    Args:
        name: Payee name, at most 500 characters (required)

    Returns:
        The new payee
    """
    with repository.api() as api_client:
        response = ynab.PayeesApi(api_client).create_payee(
            repository.plan_id,
            ynab.PostPayeeWrapper(payee=ynab.PostPayee(name=name)),
        )
    repository.mark_stale("payees")
    return Payee.from_ynab(response.data.payee)


@tool(title="Rename payee", tags={"payees", WRITE}, annotations=SETS)
def rename_payee(
    payee_id: UUID,
    name: str,
    repository: YNABRepository = Shared(plan_repository),
) -> Payee:
    """Rename a payee.  Every transaction with this payee shows the new name.

    Args:
        payee_id: Payee to rename (required)
        name: New payee name, at most 500 characters (required)

    Returns:
        The renamed payee
    """
    with repository.api() as api_client:
        response = ynab.PayeesApi(api_client).update_payee(
            repository.plan_id,
            str(payee_id),
            ynab.PatchPayeeWrapper(payee=ynab.SavePayee(name=name)),
        )
    repository.mark_stale("payees", "transactions")
    return Payee.from_ynab(response.data.payee)


TOOLS: list[Callable[..., object]] = [
    list_payees,
    find_payee,
    create_payee,
    rename_payee,
]
