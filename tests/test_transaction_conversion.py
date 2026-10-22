"""
Test how a YNAB transaction becomes the Transaction the tools return.
"""

from decimal import Decimal
from uuid import UUID

import pytest
import ynab
from conftest import create_ynab_transaction
from ids import uid

from transactions import Subtransaction, Transaction, format_flag


@pytest.mark.parametrize(
    ("flag_color", "flag_name", "expected"),
    [
        (None, None, None),
        (None, "Review", None),
        ("red", None, "Red"),
        ("purple", "Reimbursable", "Reimbursable (Purple)"),
    ],
)
def test_format_flag(
    flag_color: str | None, flag_name: str | None, expected: str | None
) -> None:
    assert format_flag(flag_color, flag_name) == expected


def test_transaction_shows_the_flag_name_and_color() -> None:
    txn = create_ynab_transaction(flag_color=ynab.TransactionFlagColor.BLUE).model_copy(
        update={"flag_name": "Tax deductible"}
    )

    assert Transaction.from_ynab(txn).flag == "Tax deductible (Blue)"


def test_transaction_keeps_the_transfer_account_and_bank_payee() -> None:
    txn = create_ynab_transaction(
        transfer_account_id=uid("acc-savings"),
        import_payee_name_original="ONLINE TRANSFER TO SAV 1234",
    )

    transaction = Transaction.from_ynab(txn)

    assert transaction.transfer_account_id == uid("acc-savings")
    assert transaction.import_payee_name_original == "ONLINE TRANSFER TO SAV 1234"


def test_transaction_without_parts_has_no_subtransactions() -> None:
    assert Transaction.from_ynab(create_ynab_transaction()).subtransactions is None


def create_ynab_subtransaction(
    *,
    id: str,
    amount: int,
    payee_id: UUID | None = None,
    payee_name: str | None = None,
    deleted: bool = False,
) -> ynab.SubTransaction:
    """Create one part of the split transaction "txn-split"."""
    return ynab.SubTransaction(
        id=id,
        transaction_id="txn-split",
        amount=amount,
        payee_id=payee_id,
        payee_name=payee_name,
        category_id=uid(f"cat-{id}"),
        category_name=f"Category {id}",
        deleted=deleted,
    )


def test_split_drops_deleted_parts_and_parts_inherit_the_parent_payee() -> None:
    txn = create_ynab_transaction(
        id="txn-split",
        amount=-80_000,
        payee_id=uid("payee-target"),
        payee_name="Target",
        subtransactions=[
            create_ynab_subtransaction(id="sub-groceries", amount=-50_000),
            create_ynab_subtransaction(
                id="sub-gift",
                amount=-30_000,
                payee_id=uid("payee-niece"),
                payee_name="Niece",
            ),
            create_ynab_subtransaction(id="sub-gone", amount=-10_000, deleted=True),
        ],
    )

    transaction = Transaction.from_ynab(txn)

    assert transaction.subtransactions == [
        Subtransaction(
            id="sub-groceries",
            amount=Decimal("-50"),
            memo=None,
            payee_id=uid("payee-target"),
            payee_name="Target",
            category_id=uid("cat-sub-groceries"),
            category_name="Category sub-groceries",
        ),
        Subtransaction(
            id="sub-gift",
            amount=Decimal("-30"),
            memo=None,
            payee_id=uid("payee-niece"),
            payee_name="Niece",
            category_id=uid("cat-sub-gift"),
            category_name="Category sub-gift",
        ),
    ]
