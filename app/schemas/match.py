from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.match import MatchStatus


class MatchBase(BaseModel):
    external_id: Optional[str] = None
    home_team: str
    away_team: str
    match_date: datetime
    status: MatchStatus = MatchStatus.scheduled
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    competition_id: int


class MatchCreate(MatchBase):
    pass


class MatchRead(MatchBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
