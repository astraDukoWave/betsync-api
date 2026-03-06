from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.dependencies import get_db, get_redis
from app.schemas.dashboard import DashboardSummary, SegmentResponse
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard")


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sport_id: Optional[UUID] = None,
    competition_id: Optional[UUID] = None,
    market: Optional[str] = None,
    sportsbook_id: Optional[UUID] = None,
    grade: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    return await dashboard_service.get_summary(
        db, redis,
        date_from=date_from, date_to=date_to,
        sport_id=sport_id, competition_id=competition_id,
        market=market, sportsbook_id=sportsbook_id,
        grade=grade,
    )


@router.get("/segments", response_model=list[SegmentResponse])
async def get_segments(
    group_by: str = Query(default="selection", pattern="^(selection|market|competition|sportsbook|grade)$"),
    db: AsyncSession = Depends(get_db),
):
    return await dashboard_service.get_segments(db, group_by=group_by)
