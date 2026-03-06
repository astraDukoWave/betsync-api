from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.pick import Pick, PickGrade, PickResult
from app.models.odd import Odd
from app.schemas.pick import PickCreate, PickRead


CONFIDENCE_THRESHOLDS = {
    PickGrade.A: Decimal("0.70"),
    PickGrade.B: Decimal("0.55"),
    PickGrade.C: Decimal("0.00"),
}


def _assign_grade(confidence: Decimal) -> PickGrade:
    if confidence >= Decimal("0.70"):
        return PickGrade.A
    elif confidence >= Decimal("0.55"):
        return PickGrade.B
    return PickGrade.C


class PickService:

    @staticmethod
    def create(db: Session, data: PickCreate) -> Pick:
        grade = _assign_grade(data.confidence)
        pick = Pick(
            confidence=data.confidence,
            grade=grade,
            result=data.result,
            reasoning=data.reasoning,
            suggested_stake=data.suggested_stake,
            match_id=data.match_id,
            odd_id=data.odd_id,
        )
        db.add(pick)
        db.commit()
        db.refresh(pick)
        return pick

    @staticmethod
    def get_by_id(db: Session, pick_id: int) -> Optional[Pick]:
        return db.query(Pick).filter(Pick.id == pick_id).first()

    @staticmethod
    def list_top(db: Session, grade: PickGrade = PickGrade.A, limit: int = 10) -> List[Pick]:
        """Return top picks filtered by grade (A = high confidence)."""
        return (
            db.query(Pick)
            .filter(Pick.grade == grade, Pick.result == PickResult.pending)
            .order_by(Pick.confidence.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_result(db: Session, pick_id: int, result: PickResult) -> Optional[Pick]:
        pick = db.query(Pick).filter(Pick.id == pick_id).first()
        if pick:
            pick.result = result
            db.commit()
            db.refresh(pick)
        return pick
