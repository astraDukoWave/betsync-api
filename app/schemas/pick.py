from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime
from app.models.pick import PickResult, PickGrade


class PickBase(BaseModel):
    confidence: Decimal
    grade: PickGrade = PickGrade.B
    result: PickResult = PickResult.pending
    reasoning: Optional[str] = None
    suggested_stake: Optional[Decimal] = None
    match_id: int
    odd_id: int


class PickCreate(PickBase):
    pass


class PickRead(PickBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
