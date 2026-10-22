"""
Test the server's tool set and its read-only mode.
"""

import runpy

import fastmcp
import pytest

from effects import READ, WRITE


async def tags_of_served_tools() -> list[set[str]]:
    module = runpy.run_module("server")
    async with fastmcp.Client(module["mcp"]) as client:
        tools = await client.list_tools()
    return [set(tool.meta["fastmcp"]["tags"]) for tool in tools]


async def test_every_tool_is_tagged_read_or_write() -> None:
    tags = await tags_of_served_tools()

    assert all(len(tool_tags & {READ, WRITE}) == 1 for tool_tags in tags)
    assert any(WRITE in tool_tags for tool_tags in tags)


async def test_read_only_mode_serves_only_read_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YNAB_READ_ONLY", "1")

    tags = await tags_of_served_tools()

    assert tags
    assert all(READ in tool_tags for tool_tags in tags)


async def test_parameter_descriptions_carry_no_docstring_indentation() -> None:
    """A wrapped Args line needs a 4-space hanging indent.  Aligned
    indentation survives FastMCP's docstring parsing and reaches the model."""
    module = runpy.run_module("server")
    async with fastmcp.Client(module["mcp"]) as client:
        tools = await client.list_tools()

    descriptions = [
        f"{tool.name}.{name}: {schema['description']!r}"
        for tool in tools
        for name, schema in tool.input_schema["properties"].items()
        if "\n " in schema.get("description", "")
    ]
    assert descriptions == []
