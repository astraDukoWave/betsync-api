from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.match import Match
from app.schemas.match import MatchCreate, MatchRead


class MatchService:
    """Service layer for Match CRUD and query operations."""

    @staticmethod
    def create(db: Session, data: MatchCreate) -> Match:
        """Persist a new match record."""
        match = Match(**data.model_dump())
        db.add(match)
        db.commit()
        db.refresh(match)
        return match

    @staticmethod
    def get_by_id(db: Session, match_id: int) -> Optional[Match]:
        """Retrieve a match by its primary key."""
        return db.query(Match).filter(Match.id == match_id).first()

    @staticmethod
    def list_all(db: Session, skip: int = 0, limit: int = 100) -> List[Match]:
        """Return a paginated list of all matches."""
        return db.query(Match).offset(skip).limit(limit).all()

    @staticmethod
    def list_by_competition(
        db: Session, competition_id: int, skip: int = 0, limit: int = 100
    ) -> List[Match]:
        """Return matches filtered by competition."""
        return (
            db.query(Match)
            .filter(Match.competition_id == competition_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_status(db: Session, match_id: int, new_status: str) -> Optional[Match]:
        """Update the status of an existing match."""
        match = db.query(Match).filter(Match.id == match_id).first()
        if match:
            match.status = new_status
            db.commit()
            db.refresh(match)
        return match

    @staticmethod
    def delete(db: Session, match_id: int) -> bool:
        """Delete a match record. Returns True if deleted."""
        match = db.query(Match).filter(Match.id == match_id).first()
        if match:
            db.delete(match)
            db.commit()
            return True
        return False
