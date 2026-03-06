from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CompetitionCreate(BaseModel):
    sport_id: UUID
    name: str
    country: str
    tier: str = "A"
    is_active: bool = True


class CompetitionResponse(BaseModel):
    competition_id: UUID
    sport_id: UUID
    name: str
    country: str
    tier: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
