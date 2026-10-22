"""
Readable identifiers for YNAB test data.

The YNAB SDK types most entity ids as UUIDs, so test data can't use names like
"cat-groceries" directly.  uid() turns a readable name into a stable UUID, so a
test can say which entity it means and still pass the SDK's validation.
"""

from uuid import UUID, uuid5

NAMESPACE = UUID("6f1b8f5e-3c55-4c64-9d0f-0c7f7c4b2a10")


def uid(name: str) -> UUID:
    """Return the same UUID for the same name, every time."""
    return uuid5(NAMESPACE, name)
