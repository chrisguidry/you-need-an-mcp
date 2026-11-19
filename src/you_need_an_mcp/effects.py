"""
What each tool does to the plan, declared the same way for every tool.

MCP clients read tool annotations to decide when to ask the user before a call:
a client can run a read without asking, and confirm a delete first.  Every tool
also carries a "read" or "write" tag, which is what YNAB_READ_ONLY uses to
switch the write tools off.

Every tool works on one YNAB plan and nothing else, so none of them is "open
world" in the MCP sense.
"""

from mcp.types import ToolAnnotations

READ = "read"
WRITE = "write"

# Only reads the plan.
READS = ToolAnnotations(read_only_hint=True, open_world_hint=False)

# Adds something new and changes nothing that exists.  Calling it twice adds
# two of them.
ADDS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)

# Overwrites fields with the values given.  Calling it twice with the same
# values leaves the plan the same as calling it once.
SETS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)

# Changes amounts relative to what is there now, so calling it twice changes
# them twice.
ADJUSTS = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)

# Removes something.  Removing it again does nothing more.
REMOVES = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)
