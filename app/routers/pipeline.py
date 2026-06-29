import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.config import settings
from app.core.dependencies import get_db, get_redis
from app.core.exceptions import ConflictError
from app.models.pick import PickSource, PickStatus
from app.schemas.pipeline import (
    PipelineRunRequest, PipelineJobResponse, PipelineTriggerResponse,
)
from app.schemas.pick import PickResponse
from app.services import pick_service

router = APIRouter(prefix="/pipeline")


@router.post("/run", response_model=PipelineTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_pipeline(
    body: PipelineRunRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    run_date = body.run_date or date.today()
    ran_key = f"pipeline:ran:{run_date}"

    if not body.force:
        already_ran = await redis.get(ran_key)
        if already_ran:
            raise ConflictError(
                "PIPELINE_ALREADY_RAN",
                f"Pipeline already ran for {run_date}. Use force=true to override.",
            )

    job_id = str(uuid.uuid4())
    await redis.set(
        f"job:{job_id}",
        '{"status":"queued","picks_suggested":null,"parlays_suggested":null}',
        ex=86400,
    )

    from app.worker.tasks import run_pipeline_task
    run_pipeline_task.apply_async(
        kwargs={"job_id": job_id, "run_date": str(run_date)},
        queue="pipeline",
    )

    return PipelineTriggerResponse(
        job_id=job_id,
        status="queued",
        message=f"Pipeline enqueued for {run_date}. Poll /pipeline/jobs/{job_id} for status.",
    )


@router.get("/jobs/{job_id}", response_model=PipelineJobResponse)
async def get_job_status(
    job_id: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    import json
    raw = await redis.get(f"job:{job_id}")
    if not raw:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("JOB_NOT_FOUND", f"Job {job_id} not found")

    data = json.loads(raw)
    return PipelineJobResponse(job_id=job_id, **data)


@router.get("/suggestions", response_model=list[PickResponse])
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
):
    items, _ = await pick_service.list_picks(
        db,
        source=PickSource.pipeline,
        status=PickStatus.pending,
        limit=50,
    )
    return items


# ── DEV-ONLY ─────────────────────────────────────────────────────────────────
# This endpoint is only available when DEBUG=true. It exists to support fast
# local iteration cycles without restarting the DB.
# NEVER expose this in production (DEBUG must be false).
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/dev/reset",
    status_code=status.HTTP_200_OK,
    summary="[DEV-ONLY] Reset pipeline data",
    description=(
        "Deletes all pipeline picks, parlay_picks, parlays, World Cup matches "
        "and Redis pipeline keys. Only available when DEBUG=true. "
        "Use `python scripts/reset_pipeline_data.py` for the same effect from CLI."
    ),
    tags=["pipeline-dev"],
)
async def dev_reset_pipeline(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """DEV-ONLY: clear pipeline state so the pipeline can be re-run cleanly."""
    if not settings.debug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only available when DEBUG=true.",
        )

    from sqlalchemy import text

    # FK-safe deletion order
    r1 = await db.execute(
        text("""
            DELETE FROM parlay_picks
            WHERE pick_id IN (
                SELECT pick_id FROM picks WHERE source = 'pipeline'
            )
        """)
    )
    r2 = await db.execute(text("DELETE FROM picks WHERE source = 'pipeline'"))
    r3 = await db.execute(text("DELETE FROM parlays"))
    r4 = await db.execute(
        text("""
            DELETE FROM matches
            WHERE competition_id IN (
                SELECT competition_id FROM competitions
                WHERE name ILIKE '%World Cup%'
            )
        """)
    )
    await db.commit()

    # Flush Redis pipeline keys
    patterns = ["pipeline:ran:*", "job:*", "odds:idempotency:*"]
    redis_deleted = 0
    for pattern in patterns:
        keys = await redis.keys(pattern)
        if keys:
            await redis.delete(*keys)
            redis_deleted += len(keys)

    return {
        "deleted": {
            "parlay_picks": r1.rowcount,
            "picks": r2.rowcount,
            "parlays": r3.rowcount,
            "matches": r4.rowcount,
            "redis_keys": redis_deleted,
        },
        "message": "Pipeline data reset. Run POST /pipeline/run to regenerate.",
    }
