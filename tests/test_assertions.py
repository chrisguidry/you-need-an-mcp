"""Test assertion helpers."""

import pytest
from assertions import extract_response_data


def test_extract_response_data_invalid_type() -> None:
    """Test that extract_response_data raises TypeError for invalid input."""
    with pytest.raises(TypeError, match="Expected CallToolResult with content"):
        extract_response_data("invalid_input")


def test_extract_response_data_invalid_list() -> None:
    """Test that extract_response_data raises TypeError for old list format."""
    with pytest.raises(TypeError, match="Expected CallToolResult with content"):
        extract_response_data([])
