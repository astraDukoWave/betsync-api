import logging
from typing import List, Dict, Any, Optional

import httpx
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class OddsAPIError(Exception):
    pass


def _is_retryable_status(response: httpx.Response) -> bool:
    return response.status_code in (429, 500, 502, 503, 504)


class OddsApiClient:
    """Synchronous HTTP client for the-odds-api.com v4."""

    def __init__(self, api_key: str, base_url: str = "https://api.the-odds-api.com/v4"):
        self.api_key = api_key
        self.base_url = base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    def get_odds(
        self,
        sport: str,
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
        odds_format: str = "american",
    ) -> List[Dict[str, Any]]:
        with httpx.Client(timeout=15) as client:
            response = client.get(
                f"{self.base_url}/sports/{sport}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": regions,
                    "markets": markets,
                    "oddsFormat": odds_format,
                },
            )

            remaining = response.headers.get("x-requests-remaining")
            if remaining:
                logger.info("Odds API quota remaining: %s", remaining)

            if response.status_code == 401:
                raise OddsAPIError("Invalid API key")
            if response.status_code == 422:
                raise OddsAPIError(f"Invalid request: {response.text}")
            if _is_retryable_status(response):
                raise httpx.TimeoutException(f"Retryable status {response.status_code}")

            response.raise_for_status()
            return response.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    def get_scores(self, sport: str, days_from: int = 1) -> List[Dict[str, Any]]:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{self.base_url}/sports/{sport}/scores",
                params={
                    "apiKey": self.api_key,
                    "daysFrom": days_from,
                },
            )
            response.raise_for_status()
            return response.json()
