"""
Test entering a scheduled transaction before its date.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
import ynab
from assertions import extract_response_data
from conftest import (
    create_ynab_transaction,
    scheduled_part,
    scheduled_response,
    scheduled_transaction,
)
from fastmcp.client import Client, FastMCPTransport
from fastmcp.exceptions import ToolError
from ids import uid

from transaction_entry import CHANGED_BY_TRANSACTIONS

# The rent is due on the last day of each month.  Its next date is the last
# day of February, and the one after that is March 31, not March 29.
RENT = scheduled_transaction(
    date_first=date(2024, 1, 31),
    date_next=date(2024, 2, 29),
    flag_color=ynab.TransactionFlagColor.RED,
)


def saved_transactions(
    transaction: ynab.TransactionDetail | None,
) -> ynab.SaveTransactionsResponse:
    return ynab.SaveTransactionsResponse(
        data=ynab.SaveTransactionsResponseData(
            transaction_ids=[transaction.id] if transaction else [],
            transaction=transaction,
            server_knowledge=1,
        )
    )


@pytest.fixture
def entered(transactions_api: MagicMock) -> None:
    """What YNAB returns when it creates the entered rent payment."""
    transactions_api.create_transaction.return_value = saved_transactions(
        create_ynab_transaction(
            id="txn-rent",
            transaction_date=date.today(),
            amount=-1_500_000,
            account_id=uid("acc-checking"),
        )
    )


def schedule(api: MagicMock, detail: ynab.ScheduledTransactionDetail = RENT) -> None:
    """Put a schedule in YNAB, and have YNAB return it when it moves."""
    api.get_scheduled_transaction_by_id.return_value = scheduled_response(detail)
    api.update_scheduled_transaction.return_value = scheduled_response(
        detail.model_copy(update={"date_next": date(2024, 3, 31)})
    )


async def test_enter_scheduled_transaction_today_with_the_scheduled_amount(
    entered: None,
    mock_repository: MagicMock,
    scheduled_transactions_api: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    schedule(scheduled_transactions_api)

    result = await mcp_client.call_tool(
        "enter_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent"))},
    )

    response = extract_response_data(result)
    assert response["transaction"]["id"] == "txn-rent"
    assert response["schedule"]["date_next"] == "2024-03-31"
    plan_id, wrapper = transactions_api.create_transaction.call_args.args
    assert plan_id == "test_plan_id"
    assert wrapper.transaction == ynab.NewTransaction(
        account_id=uid("acc-checking"),
        date=date.today(),
        amount=-1_500_000,
        payee_id=uid("payee-landlord"),
        category_id=uid("cat-rent"),
        memo="Rent",
        cleared=ynab.TransactionClearedStatus.UNCLEARED,
        approved=True,
        flag_color=ynab.TransactionFlagColor.RED,
    )
    mock_repository.mark_stale.assert_called_once_with(*CHANGED_BY_TRANSACTIONS)


@pytest.mark.parametrize(
    ("arguments", "field", "expected"),
    [
        ({"date": "2024-02-27"}, "var_date", date(2024, 2, 27)),
        ({"amount": "-1525.50"}, "amount", -1_525_500),
        ({"amount": "0"}, "amount", 0),
        ({"memo": "Paid early"}, "memo", "Paid early"),
        ({"memo": ""}, "memo", ""),
    ],
)
async def test_enter_scheduled_transaction_with_a_different_value(
    entered: None,
    scheduled_transactions_api: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    arguments: dict[str, Any],
    field: str,
    expected: object,
) -> None:
    schedule(scheduled_transactions_api)

    await mcp_client.call_tool(
        "enter_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent")), **arguments},
    )

    wrapper = transactions_api.create_transaction.call_args.args[1]
    assert getattr(wrapper.transaction, field) == expected


async def test_enter_scheduled_transaction_moves_the_schedule_to_its_next_date(
    entered: None,
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    schedule(scheduled_transactions_api)

    await mcp_client.call_tool(
        "enter_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent")), "amount": "-1525.50"},
    )

    plan_id, scheduled_id, wrapper = (
        scheduled_transactions_api.update_scheduled_transaction.call_args.args
    )
    assert (plan_id, scheduled_id) == ("test_plan_id", str(uid("st-rent")))
    assert wrapper.scheduled_transaction == ynab.SaveScheduledTransaction(
        account_id=uid("acc-checking"),
        date=date(2024, 3, 31),
        amount=-1_500_000,
        frequency=ynab.ScheduledTransactionFrequency.MONTHLY,
        payee_id=uid("payee-landlord"),
        category_id=uid("cat-rent"),
        memo="Rent",
        flag_color=ynab.TransactionFlagColor.RED,
    )


async def test_enter_scheduled_transaction_deletes_a_one_time_schedule(
    entered: None,
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    schedule(scheduled_transactions_api, scheduled_transaction(frequency="never"))

    result = await mcp_client.call_tool(
        "enter_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent"))},
    )

    assert extract_response_data(result)["schedule"] is None
    scheduled_transactions_api.delete_scheduled_transaction.assert_called_once_with(
        "test_plan_id", str(uid("st-rent"))
    )
    scheduled_transactions_api.update_scheduled_transaction.assert_not_called()


@pytest.mark.parametrize(
    ("detail", "message"),
    [
        (
            scheduled_transaction(subtransactions=[scheduled_part("water", -40_000)]),
            "split",
        ),
        (
            scheduled_transaction(frequency="twiceAMonth"),
            "twiceAMonth schedule.  Enter it in YNAB instead",
        ),
    ],
)
async def test_enter_scheduled_transaction_refuses_before_writing(
    scheduled_transactions_api: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    detail: ynab.ScheduledTransactionDetail,
    message: str,
) -> None:
    schedule(scheduled_transactions_api, detail)

    with pytest.raises(ToolError, match=message):
        await mcp_client.call_tool(
            "enter_scheduled_transaction",
            {"scheduled_transaction_id": str(uid("st-rent"))},
        )

    transactions_api.create_transaction.assert_not_called()


async def test_enter_scheduled_transaction_rolls_back_if_the_schedule_fails(
    entered: None,
    scheduled_transactions_api: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    schedule(scheduled_transactions_api)
    scheduled_transactions_api.update_scheduled_transaction.side_effect = (
        ynab.ApiException(status=503, reason="Service Unavailable")
    )

    with pytest.raises(ToolError, match="YNAB returned 503"):
        await mcp_client.call_tool(
            "enter_scheduled_transaction",
            {"scheduled_transaction_id": str(uid("st-rent"))},
        )

    transactions_api.delete_transaction.assert_called_once_with(
        "test_plan_id", "txn-rent"
    )


async def test_enter_scheduled_transaction_stops_if_ynab_returns_no_transaction(
    mock_repository: MagicMock,
    scheduled_transactions_api: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    schedule(scheduled_transactions_api)
    transactions_api.create_transaction.return_value = saved_transactions(None)

    with pytest.raises(ToolError, match="did not return the entered transaction"):
        await mcp_client.call_tool(
            "enter_scheduled_transaction",
            {"scheduled_transaction_id": str(uid("st-rent"))},
        )

    scheduled_transactions_api.update_scheduled_transaction.assert_not_called()
    mock_repository.mark_stale.assert_not_called()
