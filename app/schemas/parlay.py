from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.parlay import ParlayStatus, ParlayType
from app.models.pick import PickStatus


class ParlayCreate(BaseModel):
    sportsbook_id: UUID
    pick_ids: list[UUID] = Field(min_length=2, max_length=8)
    stake: Decimal
    type: ParlayType = ParlayType.regular


class ParlayPickDetail(BaseModel):
    pick_id: UUID
    market: str
    selection: str
    odds_decimal: Decimal
    status: PickStatus

    model_config = ConfigDict(from_attributes=True)


class ParlayResponse(BaseModel):
    parlay_id: UUID
    sportsbook_id: UUID
    run_date: date
    type: ParlayType
    stake: Decimal
    odds_total: Decimal
    potential_return: Decimal
    actual_return: Optional[Decimal] = None
    status: ParlayStatus
    picks: list[ParlayPickDetail] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @property
    def profit_loss(self) -> Optional[Decimal]:
        if self.actual_return is not None:
            return self.actual_return - self.stake
        return None
