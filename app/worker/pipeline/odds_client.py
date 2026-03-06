"""OddsApiClient (Paso 11): HTTP client for fetching live odds from the-odds-api."""
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings


class OddsApiClient:
    """Async HTTP client wrapping the-odds-api.com v4 endpoints."""

    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.odds_api_key

    async def get_sports(self) -> List[Dict[str, Any]]:
        """Fetch list of available sports from the odds API."""
        async with httpx.AsyncClient(timeout=10) as client:
            response = client.get(
                f"{self.BASE_URL}/sports",
                params={"apiKey": self.api_key, "all": "false"},
            )
            response.raise_for_status()
            return response.json()

    async def get_odds(
        self,
        sport: str,
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
        odds_format: str = "american",
    ) -> List[Dict[str, Any]]:
        """Fetch odds for a given sport and markets."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{self.BASE_URL}/sports/{sport}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": regions,
                    "markets": markets,
                    "oddsFormat": odds_format,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_scores(
        self, sport: str, days_from: int = 1
    ) -> List[Dict[str, Any]]:
        """Fetch completed game scores for settlement pipeline."""
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.BASE_URL}/sports/{sport}/scores",
                params={
                    "apiKey": self.api_key,
                    "daysFrom": days_from,
                },
            )
            response.raise_for_status()
            return response.json()
