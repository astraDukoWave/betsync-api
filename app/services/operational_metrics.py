"""Operational counters (Redis) and structured health fields for SLO-style observability."""

import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

KEY_AGG_HIT = "metrics:ops:dashboard_agg_hit"
KEY_RAW_SERVE = "metrics:ops:dashboard_raw_serve"
KEY_AGG_FALLBACK = "metrics:ops:dashboard_agg_fallback"
KEY_EXT_OK = "metrics:ops:external_api_success"
KEY_EXT_FAIL = "metrics:ops:external_api_failure"


def _enabled() -> bool:
    return bool(settings.operational_metrics_enabled)


async def incr_dashboard_agg_hit(redis) -> None:
    if not _enabled() or redis is None:
        return
    try:
        await redis.incr(KEY_AGG_HIT)
    except Exception:
        logger.debug("operational_metrics: incr_dashboard_agg_hit failed", exc_info=True)


async def incr_dashboard_raw_serve(redis) -> None:
    if not _enabled() or redis is None:
        return
    try:
        await redis.incr(KEY_RAW_SERVE)
    except Exception:
        logger.debug("operational_metrics: incr_dashboard_raw_serve failed", exc_info=True)


async def incr_dashboard_agg_fallback(redis) -> None:
    if not _enabled() or redis is None:
        return
    try:
        await redis.incr(KEY_AGG_FALLBACK)
    except Exception:
        logger.debug("operational_metrics: incr_dashboard_agg_fallback failed", exc_info=True)


def incr_external_api_result(redis, success: bool) -> None:
    if not _enabled() or redis is None:
        return
    try:
        redis.incr(KEY_EXT_OK if success else KEY_EXT_FAIL)
    except Exception:
        logger.debug("operational_metrics: incr_external_api_result failed", exc_info=True)


async def read_dashboard_ratios(redis) -> dict[str, Optional[float]]:
    """Return rolling ratio snapshots from counters (None if Redis unavailable)."""
    if redis is None:
        return {
            "agg_hit_ratio": None,
            "fallback_ratio": None,
            "external_api_success_rate": None,
        }
    try:
        raw = await redis.mget(
            KEY_AGG_HIT, KEY_RAW_SERVE, KEY_AGG_FALLBACK, KEY_EXT_OK, KEY_EXT_FAIL
        )
        agg_h, raw_s, fb, ext_ok, ext_fail = (int(x or 0) for x in raw)
        reads = agg_h + raw_s
        agg_hit_ratio = (agg_h / reads) if reads > 0 else None
        fallback_ratio = (fb / reads) if reads > 0 else None
        ext_total = ext_ok + ext_fail
        ext_rate = (ext_ok / ext_total) if ext_total > 0 else None
        return {
            "agg_hit_ratio": agg_hit_ratio,
            "fallback_ratio": fallback_ratio,
            "external_api_success_rate": ext_rate,
        }
    except Exception:
        logger.debug("operational_metrics: read_dashboard_ratios failed", exc_info=True)
        return {
            "agg_hit_ratio": None,
            "fallback_ratio": None,
            "external_api_success_rate": None,
        }


def log_operational_health(
    *,
    event: str,
    extra: dict[str, Any],
) -> None:
    """Emit a single structured log line for scrapers / log pipelines."""
    payload = {"event": event, **extra}
    logger.info("[OPS_HEALTH] %s", event, extra=payload)
