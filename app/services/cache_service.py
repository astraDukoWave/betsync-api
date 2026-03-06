import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def get_cache(redis, key: str) -> Optional[dict]:
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        logger.debug("Redis cache miss (error) for key: %s", key)
        return None


async def set_cache(redis, key: str, value: Any, ttl: int = 300) -> None:
    try:
        await redis.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        logger.debug("Redis set failed for key: %s", key)


async def delete_cache(redis, key: str) -> None:
    try:
        await redis.delete(key)
    except Exception:
        pass


async def invalidate_dashboard_cache(redis) -> None:
    try:
        keys = await redis.keys("dashboard:summary:*")
        if keys:
            await redis.delete(*keys)
    except Exception:
        logger.debug("Redis dashboard cache invalidation failed")
