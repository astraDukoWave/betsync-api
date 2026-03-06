from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SportCreate(BaseModel):
    name: str
    slug: str
    is_active: bool = True


class SportResponse(BaseModel):
    sport_id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
