from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SportsbookCreate(BaseModel):
    name: str
    currency: str = "MXN"
    odds_format_default: str = "american"
    is_active: bool = True


class SportsbookUpdate(BaseModel):
    name: str | None = None
    currency: str | None = None
    odds_format_default: str | None = None
    is_active: bool | None = None


class SportsbookResponse(BaseModel):
    sportsbook_id: UUID
    name: str
    currency: str
    odds_format_default: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
