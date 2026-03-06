from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "betsync",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Mexico_City",
    enable_utc=True,
    beat_schedule={
        # Fetch global odds every 30 minutes
        "fetch-global-odds-every-30min": {
            "task": "app.worker.tasks.fetch_and_store_odds",
            "schedule": crontab(minute="*/30"),
        },
        # Generate top picks daily at 7am MX
        "generate-daily-picks": {
            "task": "app.worker.tasks.generate_top_picks",
            "schedule": crontab(hour=7, minute=0),
        },
        # Settle parlays hourly
        "settle-open-parlays-hourly": {
            "task": "app.worker.tasks.settle_open_parlays",
            "schedule": crontab(minute=0),
        },
    },
)
