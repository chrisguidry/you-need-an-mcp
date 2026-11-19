"""Test launching through Python without a console-script executable."""

import runpy
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.usefixtures("server_unimported")


def test_module_entrypoint_starts_server() -> None:
    """Python module execution starts the same server as the console script."""
    with patch("fastmcp.FastMCP.run") as run:
        runpy.run_module("you_need_an_mcp.server", run_name="__main__")

    run.assert_called_once_with()


def test_import_does_not_start_server() -> None:
    """Loading server for a client or console script must remain passive."""
    with patch("fastmcp.FastMCP.run") as run:
        runpy.run_module("you_need_an_mcp.server")

    run.assert_not_called()
