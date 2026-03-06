from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.parlay import ParlayStatus
from app.schemas.parlay import ParlayCreate, ParlayResponse, ParlayPickDetail
from app.services import parlay_service

router = APIRouter(prefix="/parlays")


def _parlay_to_response(parlay) -> dict:
    picks = []
    for pp in parlay.parlay_picks:
        p = pp.pick
        picks.append(ParlayPickDetail(
            pick_id=p.pick_id,
            market=p.market,
            selection=p.selection,
            odds_decimal=p.odds_decimal,
            status=p.status,
        ))
    return ParlayResponse(
        parlay_id=parlay.parlay_id,
        sportsbook_id=parlay.sportsbook_id,
        run_date=parlay.run_date,
        type=parlay.type,
        stake=parlay.stake,
        odds_total=parlay.odds_total,
        potential_return=parlay.potential_return,
        actual_return=parlay.actual_return,
        status=parlay.status,
        picks=picks,
        created_at=parlay.created_at,
        updated_at=parlay.updated_at,
    )


@router.post("/", response_model=ParlayResponse, status_code=status.HTTP_201_CREATED)
async def create_parlay(
    data: ParlayCreate,
    db: AsyncSession = Depends(get_db),
):
    parlay = await parlay_service.create_parlay(db, data)
    parlay = await parlay_service.get_parlay(db, parlay.parlay_id)
    return _parlay_to_response(parlay)


@router.get("/", response_model=list[ParlayResponse])
async def list_parlays(
    parlay_status: Optional[ParlayStatus] = None,
    run_date: Optional[date] = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    parlays = await parlay_service.list_parlays(
        db, status=parlay_status, run_date=run_date, limit=limit, offset=offset,
    )
    return [_parlay_to_response(p) for p in parlays]


@router.get("/{parlay_id}", response_model=ParlayResponse)
async def get_parlay(
    parlay_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    parlay = await parlay_service.get_parlay(db, parlay_id)
    return _parlay_to_response(parlay)
