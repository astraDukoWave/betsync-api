"""Runtime gating for agg_* read paths (Phase 3 soft cutover).

Redis key blocks aggregate reads while env enables them — operational raw fallback
without process restart.
"""

AGG_RAW_FALLBACK_REDIS_KEY = "dashboard:use_raw_fallback"


async def redis_blocks_aggregate_reads(redis) -> bool:
    """True when Redis signals forced raw mode for dashboard/fiscal aggregates."""
    if redis is None:
        return False
    return bool(await redis.exists(AGG_RAW_FALLBACK_REDIS_KEY))
