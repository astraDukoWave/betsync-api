from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://betsync:betsync_pass@localhost:5432/betsync"
    database_url_sync: str = "postgresql+psycopg2://betsync:betsync_pass@localhost:5432/betsync"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # App
    secret_key: str = "changeme_in_production"
    debug: bool = False

    # Odds API
    odds_api_key: str = "your_odds_api_key_here"
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
