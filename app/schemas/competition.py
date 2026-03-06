from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CompetitionBase(BaseModel):
    name: str
    country: str
    region: str = "global"
    tier: int = 1
    external_id: Optional[str] = None
    sport_id: int


class CompetitionCreate(CompetitionBase):
    pass


class CompetitionRead(CompetitionBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
