"""
Test suite for payee-related functionality in YNAB MCP Server.
"""

from unittest.mock import MagicMock

import ynab
from assertions import extract_response_data
from conftest import create_ynab_payee
from fastmcp.client import Client, FastMCPTransport


async def test_list_payees_success(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test successful payee listing."""

    payee1 = create_ynab_payee(id="payee-1", name="Amazon")
    payee2 = create_ynab_payee(id="payee-2", name="Whole Foods")

    # Deleted payee should be excluded by default
    payee_deleted = create_ynab_payee(
        id="payee-deleted",
        name="Closed Store",
        deleted=True,
    )

    # Transfer payee
    payee_transfer = create_ynab_payee(
        id="payee-transfer",
        name="Transfer : Savings",
        transfer_account_id="acc-savings",
    )

    # Mock repository to return test payees
    mock_repository.get_payees.return_value = [
        payee2,
        payee1,
        payee_deleted,
        payee_transfer,
    ]

    result = await mcp_client.call_tool("list_payees", {})
    response_data = extract_response_data(result)

    # Should have 3 payees (deleted one excluded)
    assert len(response_data["payees"]) == 3

    # Should be sorted by name
    assert response_data["payees"][0]["name"] == "Amazon"
    assert response_data["payees"][1]["name"] == "Transfer : Savings"
    assert response_data["payees"][2]["name"] == "Whole Foods"

    # Check transfer payee details
    transfer_payee = response_data["payees"][1]
    assert transfer_payee["id"] == "payee-transfer"

    # Check pagination
    assert response_data["pagination"]["total_count"] == 3
    assert response_data["pagination"]["has_more"] is False


async def test_list_payees_pagination(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
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

    mock_repository.get_payees.return_value = payees

    # Test first page
    result = await mcp_client.call_tool("list_payees", {"limit": 2, "offset": 0})

    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["payees"]) == 2
    assert response_data["pagination"]["total_count"] == 5
    assert response_data["pagination"]["has_more"] is True

    # Should be sorted alphabetically
    assert response_data["payees"][0]["name"] == "Store 00"
    assert response_data["payees"][1]["name"] == "Store 01"


async def test_list_payees_filters_deleted(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
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

    mock_repository.get_payees.return_value = [payee_active, payee_deleted]

    result = await mcp_client.call_tool("list_payees", {})

    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only include the active payee
    assert len(response_data["payees"]) == 1
    assert response_data["payees"][0]["name"] == "Active Store"
    assert response_data["payees"][0]["id"] == "payee-active"


async def test_find_payee_filters_deleted(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
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

    mock_repository.get_payees.return_value = [payee_active, payee_deleted]

    result = await mcp_client.call_tool("find_payee", {"name_search": "amazon"})

    response_data = extract_response_data(result)
    assert response_data is not None
    # Should only find the active Amazon payee, not the deleted one
    assert len(response_data["payees"]) == 1
    assert response_data["payees"][0]["name"] == "Amazon"
    assert response_data["payees"][0]["id"] == "payee-active"


async def test_find_payee_success(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
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

    mock_repository.get_payees.return_value = payees

    # Test searching for "amazon" (case-insensitive)
    result = await mcp_client.call_tool("find_payee", {"name_search": "amazon"})

    response_data = extract_response_data(result)
    assert response_data is not None
    # Should find Amazon and Amazon Web Services, but not deleted Amazon Prime
    assert len(response_data["payees"]) == 2
    assert response_data["pagination"]["total_count"] == 2
    assert response_data["pagination"]["has_more"] is False

    # Should be sorted alphabetically
    payee_names = [p["name"] for p in response_data["payees"]]
    assert payee_names == ["Amazon", "Amazon Web Services"]


async def test_find_payee_case_insensitive(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test that payee search is case-insensitive."""

    payees = [
        ynab.Payee(
            id="payee-1",
            name="Starbucks Coffee",
            transfer_account_id=None,
            deleted=False,
        )
    ]

    mock_repository.get_payees.return_value = payees

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

        response_data = extract_response_data(result)
        assert len(response_data["payees"]) == expected_count
        if expected_count > 0:
            assert response_data["payees"][0]["name"] == "Starbucks Coffee"


async def test_find_payee_limit(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
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

    mock_repository.get_payees.return_value = payees

    # Test with limit of 2
    result = await mcp_client.call_tool(
        "find_payee", {"name_search": "store", "limit": 2}
    )

    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["payees"]) == 2
    assert response_data["pagination"]["total_count"] == 5
    assert response_data["pagination"]["has_more"] is True

    # Should be first 2 in alphabetical order
    assert response_data["payees"][0]["name"] == "Store 00"
    assert response_data["payees"][1]["name"] == "Store 01"


async def test_find_payee_no_matches(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    """Test payee search with no matching results."""

    payees = [
        ynab.Payee(
            id="payee-1", name="Starbucks", transfer_account_id=None, deleted=False
        )
    ]

    mock_repository.get_payees.return_value = payees

    result = await mcp_client.call_tool("find_payee", {"name_search": "nonexistent"})

    response_data = extract_response_data(result)
    assert response_data is not None
    assert len(response_data["payees"]) == 0
    assert response_data["pagination"]["total_count"] == 0
    assert response_data["pagination"]["has_more"] is False
