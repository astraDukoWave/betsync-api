import json
import logging
from datetime import datetime

from app.worker.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.worker.tasks.run_pipeline_task",
    bind=True,
    acks_late=True,
    max_retries=2,
    queue="pipeline",
)
def run_pipeline_task(self, job_id: str, run_date: str):
    """Execute the suggestion pipeline for a given date."""
    import redis as sync_redis
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
