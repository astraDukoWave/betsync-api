from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "betsync-api",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }
