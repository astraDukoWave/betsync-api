from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.match import MatchStatus


class MatchCreate(BaseModel):
    competition_id: UUID
    home_team: str
    away_team: str
    kickoff_at: datetime


class MatchResponse(BaseModel):
    match_id: UUID
    competition_id: UUID
    home_team: str
    away_team: str
    kickoff_at: datetime
    status: MatchStatus
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
