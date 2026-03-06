from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.dependencies import get_db, get_redis
from app.models.pick import PickGrade, PickSource, PickStatus
from app.schemas.pick import (
    PickCreate, PickUpdate, PickResolve, PickConfirm,
    PickResponse, PickListResponse,
)
from app.services import pick_service, parlay_service
from app.services.cache_service import invalidate_dashboard_cache

router = APIRouter(prefix="/picks")


@router.post("/", response_model=PickResponse, status_code=status.HTTP_201_CREATED)
async def create_pick(
    data: PickCreate,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    pick = await pick_service.create_pick(db, data)
    await invalidate_dashboard_cache(redis)
    return pick


@router.get("/", response_model=PickListResponse)
async def list_picks(
    run_date: Optional[date] = None,
    pick_status: Optional[PickStatus] = None,
    sport_id: Optional[UUID] = None,
    competition_id: Optional[UUID] = None,
    market: Optional[str] = None,
    grade: Optional[PickGrade] = None,
    source: Optional[PickSource] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    items, total = await pick_service.list_picks(
        db,
        run_date=run_date,
        status=pick_status,
        sport_id=sport_id,
        competition_id=competition_id,
        market=market,
        grade=grade,
        source=source,
        limit=limit,
        offset=offset,
    )
    return PickListResponse(
        items=items, total=total, limit=limit, offset=offset,
    )


@router.get("/{pick_id}", response_model=PickResponse)
async def get_pick(
    pick_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.get_pick(db, pick_id)


@router.patch("/{pick_id}", response_model=PickResponse)
async def update_pick(
    pick_id: UUID,
    data: PickUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.update_pick(db, pick_id, data)


@router.patch("/{pick_id}/result", response_model=PickResponse)
async def resolve_pick(
    pick_id: UUID,
    data: PickResolve,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    pick = await pick_service.resolve_pick(db, pick_id, data)
    await parlay_service.auto_resolve_parlays_for_pick(db, pick_id)
    await invalidate_dashboard_cache(redis)
    return pick


@router.delete("/{pick_id}", response_model=PickResponse)
async def delete_pick(
    pick_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.delete_pick(db, pick_id)


@router.patch("/{pick_id}/confirm", response_model=PickResponse)
async def confirm_pick(
    pick_id: UUID,
    data: PickConfirm,
    db: AsyncSession = Depends(get_db),
):
    return await pick_service.confirm_pick(db, pick_id, data)
