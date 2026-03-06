import logging
from decimal import Decimal
from typing import List

from app.worker.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.pick import Pick, PickGrade, PickResult
from app.models.parlay import Parlay, ParlayStatus
from app.services.parlay_service import ParlayService

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.fetch_and_store_odds", bind=True, max_retries=3)
def fetch_and_store_odds(self):
    """
    Fetch odds from external APIs (e.g., football-data.org, API-Football)
    for top global leagues and store them in the DB.
    Leagues targeted: Premier League, La Liga, Bundesliga, Serie A, Ligue 1,
    Liga MX, Champions League, NBA, NHL.
    """
    logger.info("[fetch_and_store_odds] Starting odds fetch for global top leagues...")
    try:
        # TODO: Implement scraper/API client for Betmaster odds
        # from app.scraper.betmaster import BetmasterScraper
        # scraper = BetmasterScraper()
        # scraper.run()
        logger.info("[fetch_and_store_odds] Completed successfully.")
        return {"status": "ok"}
    except Exception as exc:
        logger.error(f"[fetch_and_store_odds] Error: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.worker.tasks.generate_top_picks", bind=True)
def generate_top_picks(self):
    """
    Analyze stored odds and generate Grade A picks (confidence >= 0.70).
    Targets 3-5 global 'Clase A' picks per day.
    """
    logger.info("[generate_top_picks] Generating top picks...")
    db = SessionLocal()
    try:
        # TODO: Implement confidence scoring model
        # Placeholder: log existing Grade A picks count
        count = db.query(Pick).filter(
            Pick.grade == PickGrade.A,
            Pick.result == PickResult.pending
        ).count()
        logger.info(f"[generate_top_picks] {count} Grade A picks currently pending.")
        return {"status": "ok", "grade_a_count": count}
    finally:
        db.close()


@celery_app.task(name="app.worker.tasks.settle_open_parlays", bind=True)
def settle_open_parlays(self):
    """
    Check all open parlays and settle them based on their picks' results.
    Handles the 2 daily $75 parlay tickets.
    """
    logger.info("[settle_open_parlays] Settling open parlays...")
    db = SessionLocal()
    try:
        open_parlays: List[Parlay] = db.query(Parlay).filter(
            Parlay.status == ParlayStatus.open
        ).all()
        settled = 0
        for parlay in open_parlays:
            ParlayService.settle(db, parlay.id)
            settled += 1
        logger.info(f"[settle_open_parlays] Settled {settled} parlays.")
        return {"status": "ok", "settled": settled}
    finally:
        db.close()
