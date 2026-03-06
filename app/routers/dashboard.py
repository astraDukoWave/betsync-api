from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.dependencies import get_db_session
from app.models.pick import Pick
from app.models.parlay import Parlay

router = APIRouter(prefix="/dashboard")


@router.get("/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db_session)):
    """Get a high-level summary of picks and parlays."""
    total_picks = await db.scalar(select(func.count(Pick.id)))
    total_parlays = await db.scalar(select(func.count(Parlay.id)))
    return {
        "total_picks": total_picks or 0,
        "total_parlays": total_parlays or 0,
    }


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db_session)):
    """Get win/loss statistics."""
    won = await db.scalar(
        select(func.count(Pick.id)).where(Pick.result == "won")
    )
    lost = await db.scalar(
        select(func.count(Pick.id)).where(Pick.result == "lost")
    )
    pending = await db.scalar(
        select(func.count(Pick.id)).where(Pick.result == "pending")
    )
    total = (won or 0) + (lost or 0)
    win_rate = round((won or 0) / total * 100, 2) if total > 0 else 0.0
    return {
        "won": won or 0,
        "lost": lost or 0,
        "pending": pending or 0,
        "win_rate": win_rate,
    }
