from sqlalchemy.orm import Session
from typing import List, Optional

from app.models.odd import Odd
from app.schemas.odd import OddCreate, OddRead


class OddsService:
    """Service layer for Odd record management and lookups."""

    @staticmethod
    def create(db: Session, data: OddCreate) -> Odd:
        """Persist a new odds entry."""
        odd = Odd(**data.model_dump())
        db.add(odd)
        db.commit()
        db.refresh(odd)
        return odd

    @staticmethod
    def get_by_id(db: Session, odd_id: int) -> Optional[Odd]:
        """Retrieve an odds entry by primary key."""
        return db.query(Odd).filter(Odd.id == odd_id).first()

    @staticmethod
    def list_by_pick(db: Session, pick_id: int) -> List[Odd]:
        """Return all odds entries associated with a pick."""
        return db.query(Odd).filter(Odd.pick_id == pick_id).all()

    @staticmethod
    def list_by_sportsbook(db: Session, sportsbook_id: int) -> List[Odd]:
        """Return all odds entries for a specific sportsbook."""
        return db.query(Odd).filter(Odd.sportsbook_id == sportsbook_id).all()

    @staticmethod
    def get_best_odd_for_pick(db: Session, pick_id: int) -> Optional[Odd]:
        """Return the highest decimal-value odd for a given pick."""
        return (
            db.query(Odd)
            .filter(Odd.pick_id == pick_id)
            .order_by(Odd.decimal_value.desc())
            .first()
        )

    @staticmethod
    def delete(db: Session, odd_id: int) -> bool:
        """Remove an odds entry. Returns True if deleted."""
        odd = db.query(Odd).filter(Odd.id == odd_id).first()
        if odd:
            db.delete(odd)
            db.commit()
            return True
        return False
