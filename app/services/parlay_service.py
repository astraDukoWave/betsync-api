from typing import List, Optional
from decimal import Decimal
from functools import reduce
from sqlalchemy.orm import Session

from app.models.parlay import Parlay, ParlayPick, ParlayStatus
from app.models.pick import Pick, PickResult
from app.schemas.parlay import ParlayCreate


class ParlayService:

    @staticmethod
    def create(db: Session, data: ParlayCreate) -> Parlay:
        # fetch picks and validate they exist
        picks = db.query(Pick).filter(Pick.id.in_(data.pick_ids)).all()
        if not picks:
            raise ValueError("No valid picks found for the given pick_ids")

        # Calculate total combined odds
        total_odds = reduce(lambda acc, p: acc * p.odd.value, picks, Decimal("1.000"))
        potential_payout = (data.stake * total_odds).quantize(Decimal("0.01"))

        parlay = Parlay(
            name=data.name,
            stake=data.stake,
            total_odds=total_odds,
            potential_payout=potential_payout,
            status=data.status,
            notes=data.notes,
        )
        db.add(parlay)
        db.flush()  # get parlay.id without committing

        for position, pick in enumerate(picks, start=1):
            pp = ParlayPick(parlay_id=parlay.id, pick_id=pick.id, position=position)
            db.add(pp)

        db.commit()
        db.refresh(parlay)
        return parlay

    @staticmethod
    def get_by_id(db: Session, parlay_id: int) -> Optional[Parlay]:
        return db.query(Parlay).filter(Parlay.id == parlay_id).first()

    @staticmethod
    def list_open(db: Session, limit: int = 20) -> List[Parlay]:
        return (
            db.query(Parlay)
            .filter(Parlay.status == ParlayStatus.open)
            .order_by(Parlay.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def settle(db: Session, parlay_id: int) -> Optional[Parlay]:
        """Recalculate parlay status based on its picks results."""
        parlay = db.query(Parlay).filter(Parlay.id == parlay_id).first()
        if not parlay:
            return None

        results = [pp.pick.result for pp in parlay.parlay_picks]
        if PickResult.pending in results:
            parlay.status = ParlayStatus.open
        elif all(r == PickResult.won for r in results):
            parlay.status = ParlayStatus.won
            parlay.actual_payout = parlay.potential_payout
        elif all(r == PickResult.lost for r in results):
            parlay.status = ParlayStatus.lost
            parlay.actual_payout = Decimal("0.00")
        else:
            parlay.status = ParlayStatus.partial

        db.commit()
        db.refresh(parlay)
        return parlay
