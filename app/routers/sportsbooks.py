from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db
from app.models.sportsbook import Sportsbook
from app.schemas.sportsbook import SportsbookCreate, SportsbookRead
from app.services.pick_service import PickService

router = APIRouter()


@router.post("/", response_model=SportsbookRead, status_code=status.HTTP_201_CREATED)
def create_sportsbook(data: SportsbookCreate, db: Session = Depends(get_db)):
    """Register a new sportsbook."""
    existing = db.query(Sportsbook).filter(Sportsbook.name == data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sportsbook '{data.name}' already exists.",
        )
    sportsbook = Sportsbook(**data.model_dump())
    db.add(sportsbook)
    db.commit()
    db.refresh(sportsbook)
    return sportsbook


@router.get("/", response_model=List[SportsbookRead])
def list_sportsbooks(db: Session = Depends(get_db)):
    """Return all registered sportsbooks."""
    return db.query(Sportsbook).all()


@router.get("/{sportsbook_id}", response_model=SportsbookRead)
def get_sportsbook(sportsbook_id: int, db: Session = Depends(get_db)):
    """Fetch a single sportsbook by ID."""
    sportsbook = db.query(Sportsbook).filter(Sportsbook.id == sportsbook_id).first()
    if not sportsbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sportsbook not found.",
        )
    return sportsbook


@router.delete("/{sportsbook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sportsbook(sportsbook_id: int, db: Session = Depends(get_db)):
    """Remove a sportsbook record."""
    sportsbook = db.query(Sportsbook).filter(Sportsbook.id == sportsbook_id).first()
    if not sportsbook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sportsbook not found.",
        )
    db.delete(sportsbook)
    db.commit()
