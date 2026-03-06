from datetime import datetime

from fastapi import APIRouter, Depends
import redis.asyncio as aioredis

from app.core.dependencies import get_redis

router = APIRouter()


@router.get("/health")
async def health_check(redis: aioredis.Redis = Depends(get_redis)):
    redis_ok = True
    try:
        await redis.ping()
    except Exception:
        redis_ok = False

    overall = "healthy" if redis_ok else "degraded"
    return {
        "status": overall,
        "service": "betsync-api",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "components": {
            "redis": "up" if redis_ok else "down",
        },
    }
