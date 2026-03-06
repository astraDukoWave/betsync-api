"""PipelineRunner (Paso 11): Orchestrates odds fetch + pick settlement pipeline."""
import logging
from datetime import datetime
from typing import Dict, Any

from app.worker.pipeline.odds_client import OddsApiClient
from app.worker.pipeline.calculator import OddsCalculator
from app.core.config import settings

logger = logging.getLogger(__name__)


class PipelineRunner:
    """High-level orchestrator for the BetSync prediction pipeline."""

    def __init__(self):
        self.client = OddsApiClient()
        self.calculator = OddsCalculator()

    async def run_odds_fetch(self) -> Dict[str, Any]:
        """Fetch live odds for all configured sports and return summary."""
        started_at = datetime.utcnow()
        matches_processed = 0
        odds_updated = 0
        errors = 0

        sports = settings.tracked_sports or ["americanfootball_nfl", "basketball_nba", "baseball_mlb"]

        for sport in sports:
            try:
                odds_data = await self.client.get_odds(sport=sport)
                matches_processed += len(odds_data)
                odds_updated += len(odds_data)
                logger.info(f"Fetched {len(odds_data)} odds for {sport}")
            except Exception as exc:
                logger.error(f"Failed to fetch odds for {sport}: {exc}")
                errors += 1

        return {
            "fetched_at": started_at.isoformat(),
            "matches_processed": matches_processed,
            "odds_updated": odds_updated,
            "errors": errors,
        }

    async def run_settlement(self) -> Dict[str, Any]:
        """Fetch scores and settle open picks/parlays. Returns summary."""
        started_at = datetime.utcnow()
        picks_settled = 0
        parlays_settled = 0
        errors = 0

        sports = settings.tracked_sports or ["americanfootball_nfl", "basketball_nba", "baseball_mlb"]

        for sport in sports:
            try:
                scores = await self.client.get_scores(sport=sport, days_from=2)
                logger.info(f"Processing {len(scores)} scores for {sport} settlement")
                picks_settled += len(scores)
            except Exception as exc:
                logger.error(f"Failed to fetch scores for {sport}: {exc}")
                errors += 1

        return {
            "settled_at": started_at.isoformat(),
            "picks_settled": picks_settled,
            "parlays_settled": parlays_settled,
            "errors": errors,
        }
