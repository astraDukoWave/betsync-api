from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime
from app.models.odd import OddType


class OddBase(BaseModel):
    odd_type: OddType
    label: str
    value: Decimal
    bookmaker: str = "Betmaster"
    market_line: Optional[Decimal] = None
    is_open: int = 1
    match_id: int


class OddCreate(OddBase):
    pass


class OddRead(OddBase):
    id: int
    fetched_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
