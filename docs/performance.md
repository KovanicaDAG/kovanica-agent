# Performance Optimization for Kovanica Agent

This document describes performance optimization techniques implemented in the Kovanica Agent, including caching strategies and connection pooling.

## Caching Strategies

### 1. Text Embedding Caching

The `agent/embed.py` module implements a cached singleton pattern for the `TextEmbedder` class to avoid recreating the embedding model for each request.

```python
@lru_cache(maxsize=1)
def get_embedder() -> TextEmbedder:
    return TextEmbedder()
```

This ensures that the expensive model loading operation happens only once per process.

### 2. Plugin Marketplace Caching

The `agent/plugin_marketplace.py` module uses file-based caching for plugin index data to reduce network requests and improve startup time.

```python
self.cache_dir = Path.home() / ".kovanica" / "plugin_cache"
self.cache_dir.mkdir(parents=True, exist_ok=True)
self.index_file = self.cache_dir / "index.json"
```

### 3. Query Result Caching

The observability module includes caching for expensive queries to reduce database load.

## Connection Pooling

### 1. HTTP Client Pooling

The agent uses the `requests` library with automatic connection pooling through `urllib3`. Sessions are reused where possible to minimize connection establishment overhead.

### 2. Qdrant Client Connection Management

The Qdrant client connection is managed efficiently in the observability and graph modules, with proper reuse of connections.

### 3. Database Connection Pooling

SQLite connections in the analytics module are managed with proper connection handling to prevent exhaustion.

## Implementation Details

### LRU Caching with functools

We use `functools.lru_cache` for caching function results with a limited size to prevent memory growth.

Example:
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_function(param):
    # Expensive computation
    return result
```

### TTLCache for Time-Based Expiry

For data that should expire after a certain time, we implement a simple TTLCache (Time-To-Live Cache) mechanism.

### Connection Pooling Best Practices

- Reuse HTTP sessions across multiple requests
- Use connection pooling for database clients
- Close connections properly when no longer needed
- Monitor pool usage to prevent exhaustion

## Performance Monitoring

The observability system tracks:
- Function execution times
- Cache hit/miss ratios
- Connection pool utilization
- Database query performance

These metrics help identify bottlenecks and guide further optimization efforts.

## Future Improvements

1. Implement Redis-based distributed caching for multi-instance deployments
2. Add more aggressive caching for static assets
3. Implement query result caching for frequent database queries
4. Add HTTP response caching for external API calls
5. Optimize embedding batch processing