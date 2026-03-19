import json
import logging
import time
from datetime import date, datetime

import redis as sync_redis

from app.worker.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

AGG_LOCK_PREFIX = "agg_lock:"


def enqueue_recompute_aggregates_for_day(run_date: date) -> None:
    """Best-effort debounce: skip enqueue if a recompute lock is already held."""
    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    key = f"{AGG_LOCK_PREFIX}{run_date.isoformat()}"
    if r.exists(key):
        return
    recompute_aggregates_for_day.delay(run_date.isoformat())


@celery_app.task(
    name="app.worker.tasks.run_pipeline_task",
    bind=True,
    acks_late=True,
    max_retries=2,
    queue="pipeline",
)
def run_pipeline_task(self, job_id: str, run_date: str):
    """Execute the suggestion pipeline for a given date."""
    from app.core.database import SyncSessionLocal
    from app.worker.pipeline.runner import PipelineRunner

    r = sync_redis.from_url(settings.redis_url, decode_responses=True)

    try:
        r.set(f"job:{job_id}", json.dumps({
            "status": "running",
            "picks_suggested": None,
            "parlays_suggested": None,
        }), ex=86400)

        started_at = datetime.utcnow()
        db = SyncSessionLocal()

        try:
            runner = PipelineRunner(db=db, settings=settings)
            result = runner.run(run_date=run_date)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        duration = (datetime.utcnow() - started_at).total_seconds()

        r.set(f"job:{job_id}", json.dumps({
            "status": "completed",
            "picks_suggested": result.get("picks_suggested", 0),
            "parlays_suggested": result.get("parlays_suggested", 0),
            "completed_at": datetime.utcnow().isoformat(),
            "duration_sec": round(duration, 2),
        }), ex=86400)

        r.set(f"pipeline:ran:{run_date}", "1", ex=86400)

        logger.info(
            "Pipeline completed for %s: %d picks, %d parlays in %.1fs",
            run_date,
            result.get("picks_suggested", 0),
            result.get("parlays_suggested", 0),
            duration,
        )
        return result

    except Exception as exc:
        logger.error("Pipeline failed for %s: %s", run_date, exc)
        r.set(f"job:{job_id}", json.dumps({
            "status": "failed",
            "error": str(exc),
        }), ex=86400)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(
    name="app.worker.tasks.recompute_aggregates_for_day",
    bind=True,
    acks_late=True,
    max_retries=2,
    queue="pipeline",
)
def recompute_aggregates_for_day(self, run_date_iso: str):
    """Full-day UPSERT for agg tables; at most one effective run per lock TTL per day."""
    from app.core.database import SyncSessionLocal
    from app.services.aggregate_recompute import recompute_pick_aggregates_for_day_sync

    r = sync_redis.from_url(settings.redis_url, decode_responses=True)
    key = f"{AGG_LOCK_PREFIX}{run_date_iso}"
    t0 = time.perf_counter()
    if not r.set(key, "1", nx=True, ex=30):
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "agg_job_duration_ms=%s run_date=%s skipped=lock_active",
            duration_ms,
            run_date_iso,
        )
        return {"skipped": True, "run_date": run_date_iso}

    run_date = date.fromisoformat(run_date_iso)
    db = SyncSessionLocal()
    try:
        recompute_pick_aggregates_for_day_sync(db, run_date)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "agg_job_duration_ms=%s run_date=%s",
            duration_ms,
            run_date_iso,
        )
