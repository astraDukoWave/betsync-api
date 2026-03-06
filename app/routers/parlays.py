from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db
from app.schemas.parlay import ParlayCreate, ParlayRead
from app.services.parlay_service import ParlayService

router = APIRouter()


@router.post("/", response_model=ParlayRead, status_code=status.HTTP_201_CREATED)
def create_parlay(data: ParlayCreate, db: Session = Depends(get_db)):
    """Create a parlay ticket from a list of pick_ids. Default stake: $75."""
    try:
        return ParlayService.create(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/open", response_model=List[ParlayRead])
def list_open_parlays(limit: int = 20, db: Session = Depends(get_db)):
    return ParlayService.list_open(db, limit=limit)


@router.get("/{parlay_id}", response_model=ParlayRead)
def get_parlay(parlay_id: int, db: Session = Depends(get_db)):
    parlay = ParlayService.get_by_id(db, parlay_id)
    if not parlay:
        raise HTTPException(status_code=404, detail="Parlay not found")
    return parlay


@router.post("/{parlay_id}/settle", response_model=ParlayRead)
def settle_parlay(parlay_id: int, db: Session = Depends(get_db)):
    """Recalculate parlay result based on individual pick results."""
    parlay = ParlayService.settle(db, parlay_id)
    if not parlay:
        raise HTTPException(status_code=404, detail="Parlay not found")
    return parlay
