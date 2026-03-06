from pydantic import BaseModel
from typing import Optional, List
from decimal import Decimal
from datetime import datetime
from app.models.parlay import ParlayStatus


class ParlayPickRead(BaseModel):
    id: int
    parlay_id: int
    pick_id: int
    position: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ParlayBase(BaseModel):
    name: Optional[str] = None
    stake: Decimal = Decimal("75.00")
    total_odds: Optional[Decimal] = None
    potential_payout: Optional[Decimal] = None
    actual_payout: Optional[Decimal] = None
    status: ParlayStatus = ParlayStatus.open
    notes: Optional[str] = None


class ParlayCreate(ParlayBase):
    pick_ids: List[int] = []


class ParlayRead(ParlayBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    parlay_picks: List[ParlayPickRead] = []

    model_config = {"from_attributes": True}
