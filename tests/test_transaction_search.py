"""
Test the filters that list_transactions applies to the rows it fetches.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from assertions import extract_response_data
from conftest import create_ynab_transaction
from fastmcp.client import Client, FastMCPTransport


async def list_transaction_ids(
    mcp_client: Client[FastMCPTransport], arguments: dict[str, Any]
) -> list[str]:
    result = await mcp_client.call_tool("list_transactions", arguments)
    return [txn["id"] for txn in extract_response_data(result)["transactions"]]


@pytest.mark.parametrize(
    ("amounts", "expected"),
    [
        ({"min_amount": "-60"}, ["txn-small", "txn-medium", "txn-refund"]),
        ({"max_amount": "-60"}, ["txn-medium", "txn-large"]),
        ({"min_amount": "-100", "max_amount": "-25"}, ["txn-small", "txn-medium"]),
    ],
)
async def test_list_transactions_filters_by_amount(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
    amounts: dict[str, str],
    expected: list[str],
) -> None:
    mock_repository.get_transactions.return_value = [
        create_ynab_transaction(
            id="txn-refund", transaction_date=date(2024, 1, 1), amount=20_000
        ),
        create_ynab_transaction(
            id="txn-large", transaction_date=date(2024, 1, 2), amount=-150_000
        ),
        create_ynab_transaction(
            id="txn-medium", transaction_date=date(2024, 1, 3), amount=-60_000
        ),
        create_ynab_transaction(
            id="txn-small", transaction_date=date(2024, 1, 4), amount=-25_000
        ),
    ]

    ids = await list_transaction_ids(mcp_client, amounts)

    assert ids == expected


@pytest.mark.parametrize(
    ("text_search", "expected"),
    [
        ("kroger", ["txn-payee"]),
        ("SOCCER", ["txn-memo"]),
        ("coffee bar", ["txn-bank"]),
        ("nothing like this", []),
    ],
)
async def test_list_transactions_searches_payee_memo_and_bank_payee(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
    text_search: str,
    expected: list[str],
) -> None:
    mock_repository.get_transactions.return_value = [
        create_ynab_transaction(id="txn-payee", payee_name="Kroger"),
        create_ynab_transaction(id="txn-memo", memo="Soccer registration"),
        create_ynab_transaction(
            id="txn-bank", import_payee_name_original="SQ *COFFEE BAR 1234"
        ),
        create_ynab_transaction(id="txn-blank"),
    ]

    ids = await list_transaction_ids(mcp_client, {"text_search": text_search})

    assert ids == expected
