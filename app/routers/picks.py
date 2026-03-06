from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db
from app.models.pick import PickGrade, PickResult
from app.schemas.pick import PickCreate, PickRead
from app.services.pick_service import PickService

router = APIRouter()


@router.post("/", response_model=PickRead, status_code=status.HTTP_201_CREATED)
def create_pick(data: PickCreate, db: Session = Depends(get_db)):
    """Create a new pick with automatic grade assignment."""
    return PickService.create(db, data)


@router.get("/{pick_id}", response_model=PickRead)
def get_pick(pick_id: int, db: Session = Depends(get_db)):
    pick = PickService.get_by_id(db, pick_id)
    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")
    return pick


@router.get("/top/{grade}", response_model=List[PickRead])
def list_top_picks(
    grade: PickGrade = PickGrade.A,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """Return top picks filtered by grade. Default: Grade A (>= 0.70 confidence)."""
    return PickService.list_top(db, grade=grade, limit=limit)


@router.patch("/{pick_id}/result", response_model=PickRead)
def update_pick_result(
    pick_id: int,
    result: PickResult,
    db: Session = Depends(get_db),
):
    pick = PickService.update_result(db, pick_id, result)
    if not pick:
        raise HTTPException(status_code=404, detail="Pick not found")
    return pick
