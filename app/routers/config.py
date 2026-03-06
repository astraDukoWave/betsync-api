from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/config")


@router.get("/")
async def get_config():
    """Return non-sensitive application configuration."""
    return {
        "app_name": "BetSync API",
        "version": "1.0.0",
        "debug": settings.debug,
        "odds_api_base_url": settings.odds_api_base_url,
    }
