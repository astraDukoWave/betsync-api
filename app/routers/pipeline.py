from fastapi import APIRouter, BackgroundTasks
from app.worker.tasks import fetch_odds, settle_picks

router = APIRouter(prefix="/pipeline")


@router.post("/fetch-odds")
async def trigger_fetch_odds(background_tasks: BackgroundTasks):
    """Trigger async odds fetching via Celery."""
    task = fetch_odds.delay()
    return {"message": "Odds fetch task queued", "task_id": task.id}


@router.post("/settle-picks")
async def trigger_settle_picks(background_tasks: BackgroundTasks):
    """Trigger async pick settlement via Celery."""
    task = settle_picks.delay()
    return {"message": "Pick settlement task queued", "task_id": task.id}


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """Check the status of a Celery task."""
    from app.worker.celery_app import celery_app
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": str(result.result) if result.ready() else None,
    }
