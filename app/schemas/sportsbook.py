from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SportsbookBase(BaseModel):
    name: str
    url: Optional[str] = None
    is_active: bool = True


class SportsbookCreate(SportsbookBase):
    pass


class SportsbookRead(SportsbookBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
