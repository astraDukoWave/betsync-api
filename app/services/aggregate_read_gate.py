"""Runtime gating for agg_* read paths (Phase 3 soft cutover).

Redis key blocks aggregate reads while env enables them — operational raw fallback
without process restart.
"""

AGG_RAW_FALLBACK_REDIS_KEY = "dashboard:use_raw_fallback"
AGG_FAIL_CIRCUIT_REDIS_KEY = "agg_fail_circuit_open"
AGG_FAIL_CIRCUIT_TTL_SEC = 60


async def redis_blocks_aggregate_reads(redis) -> bool:
    """True when Redis signals forced raw mode for dashboard/fiscal aggregates."""
    if redis is None:
        return False
    return bool(await redis.exists(AGG_RAW_FALLBACK_REDIS_KEY))


async def redis_agg_fail_circuit_is_open(redis) -> bool:
    """True while post-fallback circuit is open — skip agg reads and cache invalidation storms."""
    if redis is None:
        return False
    return bool(await redis.exists(AGG_FAIL_CIRCUIT_REDIS_KEY))


async def redis_set_agg_fail_circuit(redis) -> None:
    """Open the agg-fail circuit for AGG_FAIL_CIRCUIT_TTL_SEC (throttle repeated agg attempts)."""
    if redis is None:
        return
    try:
        await redis.set(AGG_FAIL_CIRCUIT_REDIS_KEY, "1", ex=AGG_FAIL_CIRCUIT_TTL_SEC)
    except Exception:
        pass
