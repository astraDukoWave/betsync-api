import json
from typing import Any, Optional
from redis.asyncio import Redis


class CacheService:
    """Redis-backed cache service with JSON serialization."""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached value by key. Returns None on cache miss."""
        raw = await self.redis.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Store a value in cache with optional TTL (seconds)."""
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def delete(self, key: str) -> None:
        """Delete a key from cache."""
        await self.redis.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        return await self.redis.exists(key) > 0

    async def flush_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern. Returns count deleted."""
        keys = await self.redis.keys(pattern)
        if keys:
            return await self.redis.delete(*keys)
        return 0
