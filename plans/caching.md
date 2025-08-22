# YNAB Local Repository with Differential Sync

## Overview

A local-first repository pattern that serves YNAB data from memory while using background differential sync to maintain consistency. The repository mirrors YNAB data locally, enabling instant reads without API latency.

## Core Design Principles

1. **Local-First**: All reads from in-memory repository, zero API calls during normal operation
2. **Differential Sync**: Use YNAB's `server_knowledge` to fetch only changes, not full datasets
3. **Repository Pattern**: Speaks only YNAB SDK models, no MCP-specific types
4. **Single Budget**: Server operates on one budget specified by `YNAB_BUDGET` env var
5. **Background Sync**: Updates happen out-of-band, never blocking MCP tool calls

## Key Constraints

- **YNAB is source of truth**: Local repository is read-only mirror, never modifies data
- **Eventually consistent**: Repository converges to YNAB state within sync interval
- **Handle stale knowledge**: When server returns 409, fall back to full refresh
- **Thread-safe**: Multiple MCP tools can read concurrently during sync
- **Memory-only initially**: Start with dicts, defer persistence to later

## Repository Interface

```python
class YNABRepository:
    """Local repository for YNAB data with background differential sync."""

    def __init__(self, budget_id: str, api_client_factory: Callable):
        self.budget_id = budget_id  # Set once from YNAB_BUDGET env var
        self.api_client_factory = api_client_factory

        # In-memory storage - simple dicts
        self._data: dict[str, list] = {}  # entity_type -> list of entities
        self._server_knowledge: dict[str, int] = {}  # entity_type -> server_knowledge
        self._lock = threading.RLock()
        self._last_sync: datetime | None = None

    # Data access - returns YNAB SDK models directly
    def get_accounts(self) -> list[ynab.Account]:
    def get_categories(self) -> list[ynab.CategoryGroupWithCategories]:
    def get_transactions(self, since_date: date | None = None) -> list[ynab.TransactionDetail]:
    def get_payees(self) -> list[ynab.Payee]:
    def get_budget_month(self, month: date) -> ynab.MonthDetail:

    # Sync management
    def sync(self) -> None:  # Fetch deltas and update repository
    def needs_sync(self) -> bool:  # Check if sync is needed
    def last_sync_time(self) -> datetime | None:
```

## How Differential Sync Works

### Initial Load
```python
# First call without last_knowledge_of_server
response = api.get_accounts(budget_id)
# Returns: all accounts + server_knowledge: 100
self._data["accounts"] = response.data.accounts
self._server_knowledge["accounts"] = response.data.server_knowledge
```

### Delta Sync
```python
# Subsequent calls with last_knowledge_of_server
response = api.get_accounts(budget_id, last_knowledge_of_server=100)
# Returns: only changed accounts + server_knowledge: 101
# Apply changes: add/update/remove based on response
```

### Applying Deltas
```python
def apply_deltas(current: list, deltas: list) -> list:
    entity_map = {e.id: e for e in current}

    for delta in deltas:
        if delta.deleted:
            entity_map.pop(delta.id, None)
        else:
            entity_map[delta.id] = delta  # Add or update

    return list(entity_map.values())
```

## Budget Configuration Change

### Environment Variables
- **OLD**: `YNAB_DEFAULT_BUDGET` (optional, with fallback logic)
- **NEW**: `YNAB_BUDGET` (required for server startup)

The server will fail to start if `YNAB_BUDGET` is not set, making configuration explicit and removing ambiguity.

### Tool Signature Simplification
Remove `budget_id` parameter from all MCP tools since the server operates on a single budget:

```python
# Before
@mcp.tool()
def list_accounts(budget_id: str | None = None, limit: int = 100, offset: int = 0):
    budget_id = budget_id_or_default(budget_id)
    ...

# After
@mcp.tool()
def list_accounts(limit: int = 100, offset: int = 0):
    # No budget_id needed - using server's configured budget
    ...
```

This change applies to all tools: `list_accounts`, `list_categories`, `list_transactions`, `list_payees`, `get_budget_month`, etc.

Additionally, the `list_budgets` tool becomes unnecessary and should be removed since the server operates on a single configured budget.

### MCP Instructions Update
Simplify the MCP server instructions to remove budget_id complexity:

```python
mcp = FastMCP[None](
    name="YNAB",
    instructions="""
    Access to your YNAB budget data including accounts, categories, and transactions.
    The server operates on the budget configured via YNAB_BUDGET environment variable.
    All data is served from a local repository that syncs with YNAB in the background.
    """
)
```

## Integration with MCP Tools

### Current Pattern (Direct API with budget_id)
```python
@mcp.tool()
def list_accounts(budget_id: str | None = None):
    budget_id = budget_id_or_default(budget_id)
    with get_ynab_client() as api_client:
        accounts_api = ynab.AccountsApi(api_client)
        response = accounts_api.get_accounts(budget_id)
        # Process and return
```

### New Pattern (Repository without budget_id)
```python
# Global repository instance for the configured budget
_repository: YNABRepository | None = None

def get_repository() -> YNABRepository:
    global _repository
    if _repository is None:
        budget_id = os.environ["YNAB_BUDGET"]  # Required at startup
        _repository = YNABRepository(
            budget_id=budget_id,
            api_client_factory=get_ynab_client
        )
        # Initial sync to populate
        _repository.sync()
    return _repository

@mcp.tool()
def list_accounts(limit: int = 100, offset: int = 0):  # No budget_id parameter
    repo = get_repository()

    # Trigger background sync if needed (non-blocking)
    if repo.needs_sync():
        threading.Thread(target=repo.sync).start()

    # Return data instantly from repository
    accounts = repo.get_accounts()
    # Apply existing filtering/pagination
    return process_accounts(accounts)
```

## Critical Implementation Details

### Entity Types to Sync
- `accounts` - All accounts in budget
- `categories` - Category groups with nested categories
- `transactions` - Transaction history (consider date limits)
- `payees` - All payees
- `scheduled_transactions` - Scheduled/recurring transactions
- `budget_months` - Month-specific budget data (current/last/next)

### Thread Safety
- Use `threading.RLock()` for all repository data access
- Sync updates entire entity list atomically
- Reads can happen during sync (old data until sync completes)

### Error Handling
- **Network failure**: Continue serving stale data, retry sync later
- **409 (stale knowledge)**: Clear entity type, fetch all without last_knowledge
- **429 (rate limit)**: YNAB allows 200 requests/hour per token. Use exponential backoff, track request count
- **Invalid token**: Fail gracefully, log error, serve cached data

### Memory Management
- Typical budget: ~1-5MB in memory
- Consider transaction date limits (e.g., last 2 years only)
- Clear old budget month data (keep current + last + next)

## Benefits

- **Performance**: Sub-millisecond reads vs 100-500ms API calls
- **Reliability**: Works offline, degrades gracefully
- **Efficiency**: 60-80% fewer API calls after initial sync
- **User Experience**: Instant responses in MCP tools

## Future Considerations

- **Persistence**: SQLite for data survival across restarts
- **Selective Sync**: Only sync entity types actually used
- **Smart Scheduling**: Sync more frequently during business hours
- **Multi-Budget**: Support switching between budgets efficiently

## Migration Notes

### ✅ Completed Breaking Changes
1. **Environment variable**: `YNAB_DEFAULT_BUDGET` → `YNAB_BUDGET` (now required) ✅
2. **Tool signatures**: Remove `budget_id` parameter from all tools ✅
3. **Tool removal**: Delete `list_budgets` tool entirely ✅
4. **Error handling**: Server fails to start without `YNAB_BUDGET` ✅
5. **Test infrastructure**: Updated with pytest-env for environment variable support ✅

### User Impact
- Users must set `YNAB_BUDGET` before starting the server ✅
- LLMs no longer need to handle budget selection logic ✅
- Simpler, cleaner tool interfaces without optional budget_id parameters ✅

### Implementation Status
- **Phase 0: Budget ID Removal** ✅ COMPLETED
  - All 57 tests passing with 100% coverage
  - Clean foundation ready for repository pattern implementation

- **Phase 1: Repository Pattern** ✅ COMPLETED
  - ✅ YNABRepository class created with differential sync
  - ✅ Thread-safe data access with RLock
  - ✅ Delta application for add/update/delete operations
  - ✅ Lazy initialization per entity type
  - ✅ Server integration - all tools use repository
  - ✅ Background sync (non-blocking, triggered when data is stale)
  - ✅ needs_sync() method for staleness detection
  - ✅ Proper error handling (ConflictException, 429 rate limiting, fallback)
  - ✅ Initial population at server startup
  - ✅ Python logging with structured error handling
  - ✅ Test coverage migration (all 97 tests passing with 100% coverage)

- **Phase 2: Test Quality Improvements** ✅ COMPLETED
  - ✅ Hoisted all inline imports to top of test files
  - ✅ Removed unhelpful comments that just repeated code
  - ✅ Fixed poor test patterns (replaced try/except: pass with pytest.raises)
  - ✅ Consolidated duplicate test helper functions into conftest.py
  - ✅ Eliminated code duplication across 8+ test files
  - ✅ Maintained 100% test coverage throughout cleanup

## Success Criteria

1. MCP tools never wait for API calls during normal operation
2. Repository stays synchronized within 5 minutes of YNAB changes
3. All existing MCP tool functionality works unchanged (except budget_id removal)
4. Memory usage stays under 10MB for typical budgets
5. Graceful degradation when YNAB API is unavailable
