"""
Test suite for payee-related functionality in YNAB MCP Server.

Tests payee listing and search functionality with mocked YNAB API responses
to ensure correct filtering, pagination, and search behavior.
"""

import json
from unittest.mock import MagicMock, patch

import ynab
from fastmcp import Client

import server


async def test_list_payees_success(payees_api: MagicMock, mcp_client: Client):
    """Test successful payee listing."""

    payee1 = ynab.Payee(
        id="payee-1", name="Amazon", transfer_account_id=None, deleted=False
    )

    payee2 = ynab.Payee(
        id="payee-2", name="Whole Foods", transfer_account_id=None, deleted=False
    )

    # Deleted payee should be excluded by default
    payee_deleted = ynab.Payee(
        id="payee-deleted",
        name="Closed Store",
        transfer_account_id=None,
        deleted=True,
    )

    # Transfer payee
    payee_transfer = ynab.Payee(
        id="payee-transfer",
        name="Transfer : Savings",
        transfer_account_id="acc-savings",
        deleted=False,
    )

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(
            payees=[payee2, payee1, payee_deleted, payee_transfer],  # Not sorted
            server_knowledge=1000,
        )
    )

    payees_api.get_payees.return_value = payees_response

    result = await mcp_client.call_tool("list_payees", {})

    assert len(result) == 1
    response_data = json.loads(result[0].text)

    # Should have 3 payees (deleted one excluded)
    assert len(response_data["payees"]) == 3

    # Should be sorted by name
    assert response_data["payees"][0]["name"] == "Amazon"
    assert response_data["payees"][1]["name"] == "Transfer : Savings"
    assert response_data["payees"][2]["name"] == "Whole Foods"

    # Check transfer payee details
    transfer_payee = response_data["payees"][1]
    assert transfer_payee["id"] == "payee-transfer"
    assert transfer_payee["transfer_account_id"] == "acc-savings"

    # Check pagination
    assert response_data["pagination"]["total_count"] == 3
    assert response_data["pagination"]["has_more"] is False


async def test_list_payees_pagination(payees_api: MagicMock, mcp_client: Client):
    """Test payee listing with pagination."""

    # Create multiple payees
    payees = []
    for i in range(5):
        payee = ynab.Payee(
            id=f"payee-{i}",
            name=f"Store {i:02d}",  # Store 00, Store 01, etc. for predictable sorting
            transfer_account_id=None,
            deleted=False,
        )
        payees.append(payee)

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=payees, server_knowledge=1000)
    )

    payees_api.get_payees.return_value = payees_response

    # Test first page
    result = await mcp_client.call_tool("list_payees", {"limit": 2, "offset": 0})

    response_data = json.loads(result[0].text)
    assert len(response_data["payees"]) == 2
    assert response_data["pagination"]["total_count"] == 5
    assert response_data["pagination"]["has_more"] is True
    assert response_data["pagination"]["next_offset"] == 2

    # Should be sorted alphabetically
    assert response_data["payees"][0]["name"] == "Store 00"
    assert response_data["payees"][1]["name"] == "Store 01"


async def test_list_payees_filters_deleted(payees_api: MagicMock, mcp_client: Client):
    """Test that list_payees automatically filters out deleted payees."""

    # Active payee (should be included)
    payee_active = ynab.Payee(
        id="payee-active",
        name="Active Store",
        transfer_account_id=None,
        deleted=False,
    )

    # Deleted payee (should be excluded)
    payee_deleted = ynab.Payee(
        id="payee-deleted",
        name="Deleted Store",
        transfer_account_id=None,
        deleted=True,
    )

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(
            payees=[payee_active, payee_deleted], server_knowledge=1000
        )
    )

    payees_api.get_payees.return_value = payees_response

    result = await mcp_client.call_tool("list_payees", {})

    response_data = json.loads(result[0].text)
    # Should only include the active payee
    assert len(response_data["payees"]) == 1
    assert response_data["payees"][0]["name"] == "Active Store"
    assert response_data["payees"][0]["id"] == "payee-active"


async def test_find_payee_filters_deleted(payees_api: MagicMock, mcp_client: Client):
    """Test that find_payee automatically filters out deleted payees."""

    # Both payees have "amazon" in name, but one is deleted
    payee_active = ynab.Payee(
        id="payee-active", name="Amazon", transfer_account_id=None, deleted=False
    )

    payee_deleted = ynab.Payee(
        id="payee-deleted",
        name="Amazon Prime",
        transfer_account_id=None,
        deleted=True,
    )

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(
            payees=[payee_active, payee_deleted], server_knowledge=1000
        )
    )

    payees_api.get_payees.return_value = payees_response

    result = await mcp_client.call_tool("find_payee", {"name_search": "amazon"})

    response_data = json.loads(result[0].text)
    # Should only find the active Amazon payee, not the deleted one
    assert len(response_data["payees"]) == 1
    assert response_data["payees"][0]["name"] == "Amazon"
    assert response_data["payees"][0]["id"] == "payee-active"


async def test_find_payee_success(payees_api: MagicMock, mcp_client: Client):
    """Test successful payee search by name."""

    # Create payees with different names for searching
    payees = [
        ynab.Payee(
            id="payee-amazon",
            name="Amazon",
            transfer_account_id=None,
            deleted=False,
        ),
        ynab.Payee(
            id="payee-amazon-web",
            name="Amazon Web Services",
            transfer_account_id=None,
            deleted=False,
        ),
        ynab.Payee(
            id="payee-starbucks",
            name="Starbucks",
            transfer_account_id=None,
            deleted=False,
        ),
        ynab.Payee(
            id="payee-grocery",
            name="Whole Foods Market",
            transfer_account_id=None,
            deleted=False,
        ),
        ynab.Payee(
            id="payee-deleted",
            name="Amazon Prime",
            transfer_account_id=None,
            deleted=True,
        ),
    ]

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=payees, server_knowledge=1000)
    )

    payees_api.get_payees.return_value = payees_response

    # Test searching for "amazon" (case-insensitive)
    result = await mcp_client.call_tool("find_payee", {"name_search": "amazon"})

    response_data = json.loads(result[0].text)
    # Should find Amazon and Amazon Web Services, but not deleted Amazon Prime
    assert len(response_data["payees"]) == 2
    assert response_data["pagination"]["total_count"] == 2
    assert response_data["pagination"]["has_more"] is False

    # Should be sorted alphabetically
    payee_names = [p["name"] for p in response_data["payees"]]
    assert payee_names == ["Amazon", "Amazon Web Services"]


async def test_find_payee_case_insensitive(payees_api: MagicMock, mcp_client: Client):
    """Test that payee search is case-insensitive."""

    payees = [
        ynab.Payee(
            id="payee-1",
            name="Starbucks Coffee",
            transfer_account_id=None,
            deleted=False,
        )
    ]

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=payees, server_knowledge=1000)
    )

    payees_api.get_payees.return_value = payees_response

    # Test various case combinations
    search_terms_matches = [
        ("STARBUCKS", 1),
        ("starbucks", 1),
        ("StArBuCkS", 1),
        ("coffee", 1),
        ("COFFEE", 1),
        ("nonexistent", 0),  # This will test the else branch
    ]

    for search_term, expected_count in search_terms_matches:
        result = await mcp_client.call_tool("find_payee", {"name_search": search_term})

        response_data = json.loads(result[0].text)
        assert len(response_data["payees"]) == expected_count
        if expected_count > 0:
            assert response_data["payees"][0]["name"] == "Starbucks Coffee"


async def test_find_payee_limit(payees_api: MagicMock, mcp_client: Client):
    """Test payee search with limit parameter."""

    # Create multiple payees with "store" in the name
    payees = []
    for i in range(5):
        payees.append(
            ynab.Payee(
                id=f"payee-{i}",
                name=f"Store {i:02d}",  # Store 00, Store 01, etc.
                transfer_account_id=None,
                deleted=False,
            )
        )

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=payees, server_knowledge=1000)
    )

    payees_api.get_payees.return_value = payees_response

    # Test with limit of 2
    result = await mcp_client.call_tool(
        "find_payee", {"name_search": "store", "limit": 2}
    )

    response_data = json.loads(result[0].text)
    assert len(response_data["payees"]) == 2
    assert response_data["pagination"]["total_count"] == 5
    assert response_data["pagination"]["has_more"] is True
    assert response_data["pagination"]["returned_count"] == 2

    # Should be first 2 in alphabetical order
    assert response_data["payees"][0]["name"] == "Store 00"
    assert response_data["payees"][1]["name"] == "Store 01"


async def test_find_payee_no_matches(payees_api: MagicMock, mcp_client: Client):
    """Test payee search with no matching results."""

    payees = [
        ynab.Payee(
            id="payee-1", name="Starbucks", transfer_account_id=None, deleted=False
        )
    ]

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=payees, server_knowledge=1000)
    )

    payees_api.get_payees.return_value = payees_response

    result = await mcp_client.call_tool("find_payee", {"name_search": "nonexistent"})

    response_data = json.loads(result[0].text)
    assert len(response_data["payees"]) == 0
    assert response_data["pagination"]["total_count"] == 0
    assert response_data["pagination"]["has_more"] is False
    assert response_data["pagination"]["returned_count"] == 0


async def test_find_payee_budget_id_or_default(
    mock_environment_variables: None,
    payees_api: MagicMock,
    mcp_client: Client,
) -> None:
    """Test find_payee uses budget_id_or_default helper."""

    payees_response = ynab.PayeesResponse(
        data=ynab.PayeesResponseData(payees=[], server_knowledge=1000)
    )

    payees_api.get_payees.return_value = payees_response

    with patch("server.budget_id_or_default") as mock_budget_helper:
        mock_budget_helper.return_value = "default-budget-123"

        async with Client(server.mcp) as client:
            await mcp_client.call_tool("find_payee", {"name_search": "test"})

            # Should call the helper with None
            mock_budget_helper.assert_called_once_with(None)
            # Should call the API with the returned budget ID
            payees_api.get_payees.assert_called_once_with("default-budget-123")
