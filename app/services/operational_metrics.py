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
KEY_RECON_RUN = "metrics:ops:reconciliation_runs_total"
KEY_RECON_DRIFT = "metrics:ops:reconciliation_drift_detected_total"
KEY_RECON_CRITICAL = "metrics:ops:reconciliation_critical_total"


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


async def incr_reconciliation_run(redis) -> None:
    if not _enabled() or redis is None:
        return
    try:
        await redis.incr(KEY_RECON_RUN)
    except Exception:
        logger.debug("operational_metrics: incr_reconciliation_run failed", exc_info=True)


async def incr_reconciliation_drift_detected(redis) -> None:
    if not _enabled() or redis is None:
        return
    try:
        await redis.incr(KEY_RECON_DRIFT)
    except Exception:
        logger.debug(
            "operational_metrics: incr_reconciliation_drift_detected failed",
            exc_info=True,
        )


async def incr_reconciliation_critical(redis) -> None:
    if not _enabled() or redis is None:
        return
    try:
        await redis.incr(KEY_RECON_CRITICAL)
    except Exception:
        logger.debug(
            "operational_metrics: incr_reconciliation_critical failed",
            exc_info=True,
        )


async def read_reconciliation_counters(redis) -> dict[str, Optional[int]]:
    if redis is None:
        return {
            "reconciliation_runs_total": None,
            "reconciliation_drift_detected_total": None,
            "reconciliation_critical_total": None,
        }
    try:
        raw = await redis.mget(KEY_RECON_RUN, KEY_RECON_DRIFT, KEY_RECON_CRITICAL)
        run, drift, crit = (int(x or 0) for x in raw)
        return {
            "reconciliation_runs_total": run,
            "reconciliation_drift_detected_total": drift,
            "reconciliation_critical_total": crit,
        }
    except Exception:
        logger.debug(
            "operational_metrics: read_reconciliation_counters failed",
            exc_info=True,
        )
        return {
            "reconciliation_runs_total": None,
            "reconciliation_drift_detected_total": None,
            "reconciliation_critical_total": None,
        }


async def read_dashboard_ratios(redis) -> dict[str, Any]:
    """Return rolling ratio snapshots and ops counters (None values if Redis unavailable)."""
    if redis is None:
        return {
            "agg_hit_ratio": None,
            "fallback_ratio": None,
            "external_api_success_rate": None,
            "reconciliation_runs_total": None,
            "reconciliation_drift_detected_total": None,
            "reconciliation_critical_total": None,
        }
    try:
        raw = await redis.mget(
            KEY_AGG_HIT,
            KEY_RAW_SERVE,
            KEY_AGG_FALLBACK,
            KEY_EXT_OK,
            KEY_EXT_FAIL,
            KEY_RECON_RUN,
            KEY_RECON_DRIFT,
            KEY_RECON_CRITICAL,
        )
        agg_h, raw_s, fb, ext_ok, ext_fail, recon_run, recon_drift, recon_crit = (
            int(x or 0) for x in raw
        )
        reads = agg_h + raw_s
        agg_hit_ratio = (agg_h / reads) if reads > 0 else None
        fallback_ratio = (fb / reads) if reads > 0 else None
        ext_total = ext_ok + ext_fail
        ext_rate = (ext_ok / ext_total) if ext_total > 0 else None
        return {
            "agg_hit_ratio": agg_hit_ratio,
            "fallback_ratio": fallback_ratio,
            "external_api_success_rate": ext_rate,
            "reconciliation_runs_total": recon_run,
            "reconciliation_drift_detected_total": recon_drift,
            "reconciliation_critical_total": recon_crit,
        }
    except Exception:
        logger.debug("operational_metrics: read_dashboard_ratios failed", exc_info=True)
        return {
            "agg_hit_ratio": None,
            "fallback_ratio": None,
            "external_api_success_rate": None,
            "reconciliation_runs_total": None,
            "reconciliation_drift_detected_total": None,
            "reconciliation_critical_total": None,
        }


def log_operational_health(
    *,
    event: str,
    extra: dict[str, Any],
) -> None:
    """Emit a single structured log line for scrapers / log pipelines."""
    payload = {"event": event, **extra}
    logger.info("[OPS_HEALTH] %s", event, extra=payload)
