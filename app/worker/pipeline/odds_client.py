import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from app.services.operational_metrics import incr_external_api_result

logger = logging.getLogger(__name__)


class OddsAPIError(Exception):
    pass


class OddsRetryableError(Exception):
    """Transient HTTP / transport condition; safe to retry with backoff + jitter."""


def _is_retryable_status(status_code: int) -> bool:
    return status_code in (429, 500, 502, 503, 504)


def _retry_predicate(exc: BaseException) -> bool:
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            OddsRetryableError,
        ),
    )


class OddsApiClient:
    """HTTP client for the-odds-api.com v4 with backoff+jitter, pacing, and optional idempotency cache."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.the-odds-api.com/v4",
        *,
        max_requests_per_minute: int = 30,
        idempotency_ttl_seconds: int = 300,
        max_retry_attempts: int = 5,
        redis_client: Optional[Any] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._redis = redis_client
        self._idempotency_ttl = idempotency_ttl_seconds
        self._max_retries = max(1, int(max_retry_attempts))
        rpm = max(1, int(max_requests_per_minute))
        self._min_interval = 60.0 / float(rpm)
        self._last_request_mono: float = 0.0

    def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        wait = self._min_interval - (now - self._last_request_mono)
        if wait > 0:
            time.sleep(wait)
        self._last_request_mono = time.monotonic()

    def _cache_get(self, key: str) -> Optional[Any]:
        if not self._redis or not key:
            return None
        try:
            raw = self._redis.get(key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception:
            logger.debug("odds idempotency cache get failed for %s", key, exc_info=True)
            return None

    def _cache_set(self, key: str, payload: Any) -> None:
        if not self._redis or not key:
            return
        try:
            self._redis.set(
                key,
                json.dumps(payload),
                ex=self._idempotency_ttl,
            )
        except Exception:
            logger.debug("odds idempotency cache set failed for %s", key, exc_info=True)

    def _request_json(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        timeout: float,
    ) -> List[Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        max_att = self._max_retries
        redis = self._redis

        @retry(
            stop=stop_after_attempt(max_att),
            wait=wait_random_exponential(multiplier=1, min=1, max=60),
            retry=retry_if_exception(_retry_predicate),
            reraise=True,
        )
        def _attempt() -> List[Dict[str, Any]]:
            self._pace()
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, params=params)
                remaining = response.headers.get("x-requests-remaining")
                if remaining:
                    logger.info("Odds API quota remaining: %s", remaining)

                if response.status_code == 401:
                    incr_external_api_result(redis, False)
                    raise OddsAPIError("Invalid API key")
                if response.status_code == 422:
                    incr_external_api_result(redis, False)
                    raise OddsAPIError(f"Invalid request: {response.text}")
                if _is_retryable_status(response.status_code):
                    raise OddsRetryableError(
                        f"Retryable status {response.status_code}: {response.text[:200]}"
                    )

                response.raise_for_status()
                return response.json()

        try:
            data = _attempt()
            incr_external_api_result(redis, True)
            return data
        except OddsAPIError:
            raise
        except Exception:
            incr_external_api_result(redis, False)
            raise

    def get_odds(
        self,
        sport: str,
        regions: str = "us",
        markets: str = "h2h,spreads,totals",
        odds_format: str = "american",
        *,
        idempotency_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch odds; optional idempotency_key stores a successful JSON body in Redis so a retry
        after an apparent timeout does not imply divergent downstream writes.
        """
        cache_key = (
            f"odds:idempotency:{idempotency_key}" if idempotency_key else None
        )
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                logger.info(
                    "Odds API cache hit for idempotency_key=%s",
                    idempotency_key[:64] if idempotency_key else "",
                )
                return cached

        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
        }
        data = self._request_json(
            f"/sports/{sport}/odds",
            params,
            timeout=20.0,
        )
        if cache_key:
            self._cache_set(cache_key, data)
        return data

    def get_scores(self, sport: str, days_from: int = 1) -> List[Dict[str, Any]]:
        params = {
            "apiKey": self.api_key,
            "daysFrom": days_from,
        }
        return self._request_json(
            f"/sports/{sport}/scores",
            params,
            timeout=15.0,
        )
