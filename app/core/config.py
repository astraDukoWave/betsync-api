from decimal import Decimal
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://betsync:betsync_pass@localhost:5432/betsync"
    database_url_sync: str = "postgresql+psycopg2://betsync:betsync_pass@localhost:5432/betsync"

    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    secret_key: str = "changeme_in_production"
    debug: bool = False

    odds_api_key: str = "your_odds_api_key_here"
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    dashboard_cache_ttl: int = 300

    # Phase 3: when True, dashboard/fiscal may read agg_* where implemented;
    # Redis key dashboard:use_raw_fallback still forces raw without restart.
    use_aggregates_for_dashboard: bool = False

    # Domain: profit vs implied settlement (stake × odds) tolerance in currency units.
    pick_profit_tolerance: Decimal = Field(default=Decimal("0.02"))

    # External Odds API — client-side pacing and response deduplication (idempotency cache).
    odds_api_max_requests_per_minute: int = 30
    odds_api_idempotency_ttl_seconds: int = 300
    odds_api_retry_attempts: int = 5
    operational_metrics_enabled: bool = True

    # POST /api/v1/admin/reconciliation/run — required shared secret (header X-Reconciliation-Secret).
    admin_reconciliation_secret: str = ""

    # POST /picks idempotency (Redis NX lock + cached response body).
    idempotency_processing_ttl_seconds: int = 120
    idempotency_result_ttl_seconds: int = 1800

    # ── World Cup 2026 pipeline ───────────────────────────────────────────────
    # The Odds API v4 sport slug for FIFA World Cup 2026.
    # Verify available slugs: GET /v4/sports?apiKey=YOUR_KEY
    world_cup_sport_slug: str = "soccer_fifa_world_cup_2026"

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore",
    )


settings = Settings()
