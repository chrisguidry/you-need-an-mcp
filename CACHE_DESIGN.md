# YNAB Repository Pattern Caching Design

## Overview

This document specifies a Repository pattern implementation for caching YNAB data in the MCP server. The repository acts as a budget-scoped YNAB API that handles caching, delta sync, and data lifecycle management internally.

## Core Design Philosophy

**Budget-Scoped Interface**: Each repository instance is bound to a single budget, eliminating `budget_id` parameters from all method signatures.

**Clean Separation**: Repository handles data access and caching; MCP tools handle business logic and formatting.

**Delta Sync First**: Leverage YNAB's `server_knowledge` system for efficient updates.

**Pluggable Storage**: Abstract storage interface allows evolution from in-memory → SQLite → Redis.

## Architecture Overview

```
MCP Tools
    ↓
BudgetRepository (budget-scoped)
    ↓
CacheManager (data type strategies)
    ↓
StorageBackend (pluggable)
    ↓
YNAB Python SDK
```

## Primary Interfaces

### BudgetRepository

```python
class BudgetRepository:
    """Budget-scoped YNAB API with intelligent caching"""

    def __init__(self, budget_id: str, ynab_client, storage_backend: StorageBackend):
        self.budget_id = budget_id
        self.client = ynab_client
        self.cache = CacheManager(storage_backend, budget_id)

    # Structural Data (High Cache Value)
    async def get_accounts(self) -> List[Account]:
        """Get all accounts - cached with delta sync"""

    async def get_categories(self) -> List[CategoryGroup]:
        """Get category structure - cached with delta sync"""

    async def get_payees(self) -> List[Payee]:
        """Get all payees - cached with delta sync"""

    # Dynamic Data (Strategic Caching)
    async def get_budget_month(self, month: Optional[str] = None) -> BudgetMonth:
        """Get monthly budget data - short TTL cache"""

    async def get_month_category_by_id(self, category_id: str, month: Optional[str] = None) -> Category:
        """Get specific category - cached briefly"""

    # Transaction Data (Pass-through with Smart Filtering)
    async def get_transactions(self, **filters) -> List[Transaction]:
        """Get transactions - no caching, but use cached payee/category data for filtering"""

    async def get_scheduled_transactions(self, **filters) -> List[ScheduledTransaction]:
        """Get scheduled transactions - medium TTL cache"""

    # Search Operations (Leverage Cached Data)
    async def find_payee(self, name: str) -> List[Payee]:
        """Search payees using cached payee list"""

    # Cache Management
    async def refresh_structural_data(self) -> None:
        """Force refresh of accounts/categories/payees"""

    async def invalidate_cache(self) -> None:
        """Clear all cached data for this budget"""

    def get_cache_stats(self) -> CacheStats:
        """Return cache hit rates and freshness info"""
```

### StorageBackend Interface

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from datetime import datetime

class StorageBackend(ABC):
    """Abstract storage interface for cache data"""

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]:
        """Retrieve cache entry by key"""

    @abstractmethod
    async def set(self, key: str, entry: CacheEntry) -> None:
        """Store cache entry"""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete cache entry"""

    @abstractmethod
    async def clear_budget(self, budget_id: str) -> None:
        """Clear all entries for a budget"""

    @abstractmethod
    async def get_keys_with_prefix(self, prefix: str) -> List[str]:
        """Get all keys matching prefix (for cache management)"""

@dataclass
class CacheEntry:
    """Standardized cache entry format"""
    data: Any
    server_knowledge: Optional[int]
    created_at: datetime
    last_accessed: datetime
    access_count: int
    entry_type: str  # "accounts", "categories", "payees", etc.
```

### CacheManager

```python
class CacheManager:
    """Handles caching strategies per data type"""

    def __init__(self, storage: StorageBackend, budget_id: str):
        self.storage = storage
        self.budget_id = budget_id
        self.strategies = self._init_strategies()

    def _init_strategies(self) -> Dict[str, CacheStrategy]:
        """Initialize caching strategies per data type"""
        return {
            "accounts": StructuralCacheStrategy(ttl_seconds=1800),      # 30 min
            "categories": StructuralCacheStrategy(ttl_seconds=1800),    # 30 min
            "payees": StructuralCacheStrategy(ttl_seconds=3600),        # 60 min
            "budget_month": DynamicCacheStrategy(ttl_seconds=300),      # 5 min
            "scheduled_transactions": DynamicCacheStrategy(ttl_seconds=1800), # 30 min
        }

    async def get_or_fetch(self,
                          data_type: str,
                          fetch_func: Callable,
                          cache_key_suffix: str = "") -> Any:
        """Generic cache-or-fetch pattern"""

    async def invalidate_type(self, data_type: str) -> None:
        """Invalidate all cache entries of a specific type"""
```

## Caching Strategies

### 1. StructuralCacheStrategy
**Used for**: Accounts, Categories, Payees

**Characteristics**:
- Long TTL (30-60 minutes)
- Delta sync with `server_knowledge`
- Merge updates with existing data
- High cache hit rate expected

**Implementation**:
```python
class StructuralCacheStrategy(CacheStrategy):
    async def get_or_fetch(self, cache_key: str, fetch_func: Callable) -> Any:
        cached_entry = await self.storage.get(cache_key)

        # Check if cache is fresh enough
        if cached_entry and self._is_fresh(cached_entry):
            await self._update_access_stats(cached_entry)
            return cached_entry.data

        # Fetch with delta sync if we have cached data
        last_knowledge = cached_entry.server_knowledge if cached_entry else None
        response = await fetch_func(last_knowledge_of_server=last_knowledge)

        # Merge delta updates with existing data
        if cached_entry and response.data:
            merged_data = self._merge_data(cached_entry.data, response.data)
        else:
            merged_data = response.data or (cached_entry.data if cached_entry else [])

        # Update cache
        new_entry = CacheEntry(
            data=merged_data,
            server_knowledge=response.server_knowledge,
            created_at=cached_entry.created_at if cached_entry else datetime.now(),
            last_accessed=datetime.now(),
            access_count=(cached_entry.access_count if cached_entry else 0) + 1,
            entry_type=self.data_type
        )

        await self.storage.set(cache_key, new_entry)
        return merged_data
```

### 2. DynamicCacheStrategy
**Used for**: Budget Month Data, Scheduled Transactions

**Characteristics**:
- Shorter TTL (5-30 minutes)
- May use delta sync where supported
- More aggressive cache invalidation
- Balance between freshness and performance

### 3. PassThroughStrategy
**Used for**: Transactions (high volume, frequently changing)

**Characteristics**:
- No caching of transaction data itself
- Use cached structural data for filtering/enrichment
- Direct API calls for transaction queries
- Leverage cached payee/category data for faster filtering

## Data Merge Logic

### Account Merging
```python
def _merge_accounts(self, existing: List[Account], updates: List[Account]) -> List[Account]:
    """
    YNAB Delta Sync Rules for Accounts:
    - Updated accounts replace existing accounts
    - Deleted accounts (deleted=True) are removed
    - New accounts are added
    """
    existing_dict = {acc.id: acc for acc in existing}

    for updated_account in updates:
        if updated_account.deleted:
            existing_dict.pop(updated_account.id, None)
        else:
            existing_dict[updated_account.id] = updated_account

    return list(existing_dict.values())
```

### Category Merging
```python
def _merge_categories(self, existing: List[CategoryGroup], updates: List[CategoryGroup]) -> List[CategoryGroup]:
    """
    YNAB Delta Sync Rules for Categories:
    - Category groups can be updated/deleted
    - Individual categories within groups can be updated/deleted
    - Handle nested structure carefully
    """
    # Complex nested merge logic for category groups and their categories
    # Handle both group-level and category-level changes
```

### Payee Merging
```python
def _merge_payees(self, existing: List[Payee], updates: List[Payee]) -> List[Payee]:
    """
    YNAB Delta Sync Rules for Payees:
    - Payees are rarely deleted, mostly added/renamed
    - Transfer payees have special handling
    """
    # Similar to accounts but payees have special rules
```

## Integration with MCP Tools

### Before (Current)
```python
@mcp.tool()
async def list_accounts(budget_id: Optional[str] = None) -> dict:
    async with get_ynab_client() as client:
        budget_id = budget_id or get_default_budget()
        response = await client.accounts.get_accounts(budget_id)
        accounts = [acc for acc in response.data.accounts if not acc.deleted]
        # ... formatting logic
```

### After (With Repository)
```python
# Global repository cache
_repository_cache: Dict[str, BudgetRepository] = {}

async def get_budget_repository(budget_id: str) -> BudgetRepository:
    """Get or create repository for budget"""
    if budget_id not in _repository_cache:
        async with get_ynab_client() as client:
            storage = InMemoryStorageBackend()  # Or SQLiteStorageBackend()
            _repository_cache[budget_id] = BudgetRepository(budget_id, client, storage)
    return _repository_cache[budget_id]

@mcp.tool()
async def list_accounts(budget_id: Optional[str] = None) -> dict:
    budget_id = budget_id or get_default_budget()
    repo = await get_budget_repository(budget_id)

    accounts = await repo.get_accounts()  # Now cached!
    active_accounts = [acc for acc in accounts if not acc.deleted]
    # ... same formatting logic
```

## Storage Backend Implementations

### Phase 1: InMemoryStorageBackend
```python
class InMemoryStorageBackend(StorageBackend):
    """Simple in-memory storage for development and testing"""

    def __init__(self):
        self._data: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CacheEntry]:
        async with self._lock:
            entry = self._data.get(key)
            if entry:
                # Update access stats
                entry.last_accessed = datetime.now()
                entry.access_count += 1
            return entry
```

### Phase 2: SQLiteStorageBackend
```python
class SQLiteStorageBackend(StorageBackend):
    """Persistent SQLite storage for production use"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create cache tables if they don't exist"""
        # SQL schema for cache entries
        # Indexes on budget_id, entry_type, created_at
        # JSON column for data storage
```

### Phase 3: RedisStorageBackend
```python
class RedisStorageBackend(StorageBackend):
    """Redis storage for high-performance multi-client scenarios"""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

    # Redis-specific implementation with:
    # - Automatic TTL support
    # - Pub/Sub for cache invalidation
    # - Efficient key pattern matching
```

## Error Handling & Fallback Strategies

### Cache Miss Handling
```python
async def get_accounts(self) -> List[Account]:
    try:
        return await self.cache.get_or_fetch("accounts", self._fetch_accounts)
    except YNABAPIError as e:
        # If API fails, return cached data if available (even if stale)
        cached_entry = await self.cache.storage.get(f"accounts_{self.budget_id}")
        if cached_entry:
            logger.warning(f"YNAB API failed, returning stale cache: {e}")
            return cached_entry.data
        raise  # No cache available, re-raise the error
```

### Storage Backend Failures
```python
async def get_or_fetch(self, data_type: str, fetch_func: Callable) -> Any:
    try:
        # Try cache first
        return await self._get_from_cache(data_type)
    except StorageError:
        # Cache backend failed, fall back to direct API
        logger.warning("Cache storage failed, falling back to direct API")
        return await fetch_func()
```

## Performance Considerations

### Memory Management
- **LRU Eviction**: Remove least recently used entries when memory limits reached
- **Size Limits**: Configure max cache size per budget and globally
- **Compression**: Consider compressing large cached datasets

### Response Time Optimization
- **Async/Await**: All operations are async for non-blocking I/O
- **Batch Operations**: Fetch multiple data types in parallel when possible
- **Lazy Loading**: Only fetch data when requested

### YNAB API Rate Limiting
- **Respect Limits**: YNAB allows 200 requests per hour per token
- **Request Batching**: Combine multiple data fetches where possible
- **Cache Warming**: Proactively fetch commonly used data
- **Exponential Backoff**: Implement retry logic for rate limit errors

## Testing Strategy

### Unit Tests
```python
class TestBudgetRepository:
    @pytest.fixture
    async def mock_storage(self):
        return MockStorageBackend()

    @pytest.fixture
    async def mock_ynab_client(self):
        return MockYNABClient()

    @pytest.fixture
    async def repository(self, mock_storage, mock_ynab_client):
        return BudgetRepository("test-budget", mock_ynab_client, mock_storage)

    async def test_get_accounts_cache_miss(self, repository):
        """Test cache miss scenario"""
        accounts = await repository.get_accounts()
        assert len(accounts) > 0
        # Verify API was called
        # Verify data was cached

    async def test_get_accounts_cache_hit(self, repository):
        """Test cache hit scenario"""
        # Pre-populate cache
        await repository.get_accounts()  # First call
        accounts = await repository.get_accounts()  # Second call should hit cache
        # Verify API was not called second time

    async def test_delta_sync_merge(self, repository):
        """Test delta sync merging logic"""
        # Mock initial data
        # Mock delta update
        # Verify correct merging
```

### Integration Tests
```python
class TestRepositoryIntegration:
    async def test_real_ynab_api_integration(self):
        """Test against real YNAB API (with test budget)"""
        # Requires YNAB_TEST_TOKEN and YNAB_TEST_BUDGET

    async def test_storage_backend_persistence(self):
        """Test data persists across repository instances"""

    async def test_concurrent_access(self):
        """Test multiple concurrent requests to same repository"""
```

### Performance Tests
```python
class TestRepositoryPerformance:
    async def test_cache_hit_performance(self):
        """Verify cache hits are significantly faster than API calls"""

    async def test_memory_usage(self):
        """Monitor memory usage with large datasets"""

    async def test_concurrent_load(self):
        """Test performance under concurrent load"""
```

## Migration Strategy

### Phase 1: Repository Implementation
1. Implement `BudgetRepository` and `InMemoryStorageBackend`
2. Add comprehensive test suite
3. Integrate with 2-3 MCP tools as proof of concept

### Phase 2: Full MCP Integration
1. Migrate all MCP tools to use repository pattern
2. Add cache management endpoints for debugging
3. Performance testing and optimization

### Phase 3: Persistent Storage
1. Implement `SQLiteStorageBackend`
2. Add cache warming strategies
3. Production deployment and monitoring

### Phase 4: Advanced Features
1. `RedisStorageBackend` for multi-instance deployments
2. Cache invalidation via webhooks (if YNAB supports)
3. Advanced analytics and cache optimization

## Configuration

```python
@dataclass
class CacheConfig:
    """Configuration for repository caching behavior"""

    # TTL settings (seconds)
    accounts_ttl: int = 1800      # 30 minutes
    categories_ttl: int = 1800    # 30 minutes
    payees_ttl: int = 3600        # 60 minutes
    budget_month_ttl: int = 300   # 5 minutes
    scheduled_transactions_ttl: int = 1800  # 30 minutes

    # Memory limits
    max_cache_size_mb: int = 100
    max_entries_per_budget: int = 10000

    # Performance settings
    enable_compression: bool = False
    background_refresh: bool = True

    # Storage backend
    storage_type: str = "memory"  # "memory", "sqlite", "redis"
    storage_config: Dict[str, Any] = field(default_factory=dict)

# Usage
cache_config = CacheConfig(
    accounts_ttl=3600,  # 1 hour for accounts
    storage_type="sqlite",
    storage_config={"db_path": "/tmp/ynab_cache.db"}
)
```

## Future Extensions

### Webhook Integration
If YNAB ever supports webhooks, we could invalidate cache immediately when data changes:
```python
@app.post("/ynab-webhook")
async def handle_ynab_webhook(webhook_data: YNABWebhookData):
    """Invalidate relevant cache when YNAB data changes"""
    budget_id = webhook_data.budget_id
    data_type = webhook_data.data_type

    repo = await get_budget_repository(budget_id)
    await repo.cache.invalidate_type(data_type)
```

### Multi-Budget Optimization
```python
class MultiBudgetRepository:
    """Manage multiple budget repositories efficiently"""

    async def get_repository(self, budget_id: str) -> BudgetRepository:
        """Get repository with shared storage backend"""

    async def invalidate_all_budgets(self) -> None:
        """Clear cache for all budgets"""

    async def get_global_cache_stats(self) -> GlobalCacheStats:
        """Cache statistics across all budgets"""
```

### Advanced Analytics
```python
class CacheAnalytics:
    """Analyze cache performance and usage patterns"""

    def get_hit_rate_by_data_type(self) -> Dict[str, float]:
        """Cache hit rates per data type"""

    def get_most_accessed_data(self) -> List[CacheEntry]:
        """Most frequently accessed cache entries"""

    def suggest_ttl_optimizations(self) -> Dict[str, int]:
        """Suggest TTL adjustments based on usage patterns"""
```

## Implementation Notes for Future Developer

### Key Files to Create
1. `cache/repository.py` - Main `BudgetRepository` class
2. `cache/storage.py` - Storage backend interfaces and implementations
3. `cache/strategies.py` - Caching strategy implementations
4. `cache/config.py` - Configuration classes
5. `tests/test_cache_repository.py` - Comprehensive test suite

### Important YNAB SDK Details
- `server_knowledge` is returned in most response objects as `response.data.server_knowledge`
- Delta sync parameter is `last_knowledge_of_server` in SDK method calls
- Not all endpoints support delta sync (check SDK documentation)
- Transfer payees have `transfer_account_id` set and need special handling
- Deleted items have `deleted=True` and should be filtered out in most cases

### Integration Points
- Modify existing MCP tools to use `get_budget_repository(budget_id)`
- Update `get_ynab_client()` context manager to work with repository pattern
- Consider adding `@cached_mcp_tool` decorator for common patterns

### Testing Requirements
- Mock YNAB API responses with realistic data
- Test delta sync merge logic thoroughly
- Verify cache invalidation works correctly
- Performance test with household-scale data (1000s of transactions)
- Test storage backend failure scenarios

This design provides a robust foundation for intelligent YNAB data caching while maintaining clean separation of concerns and easy extensibility.
